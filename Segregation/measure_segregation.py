import os, sys
import geopandas as gpd
import pandas as pd
from tqdm import tqdm
import argparse
from statistics import mean
from scipy.spatial import cKDTree
import segregation
import numpy as np

import warnings
warnings.filterwarnings("ignore")

pd.set_option('display.max_columns', 500)
pd.set_option('display.max_rows', 10000)

parser = argparse.ArgumentParser()

parser.add_argument('-z', '--zctas', type = str, help = 'A shapefile of ZCTAs')
parser.add_argument('-d', '--districts', type = str, help = 'A shapefile of legislative districts.')
parser.add_argument('-p', '--precincts', type = str, help = 'A shapefile of precincts')
parser.add_argument('-v', '--voters', type = str, help = 'Precinct-level voter registration data with party, ethnicity, and race')

args = parser.parse_args()

precincts = gpd.read_file(args.precincts)
voters = pd.read_csv(args.voters)

precincts_long = pd.merge(precincts, voters, left_on = ['county_nam', 'prec_id'], right_on = ['county_desc', 'precinct_abbrv'])

party = precincts_long.groupby(['county_nam', 'prec_id', 'party_cd']).sum('Voters').reset_index().pivot(index = ['county_nam', 'prec_id'], columns = 'party_cd', values = 'Voters').reset_index()
race = precincts_long.groupby(['county_nam', 'prec_id', 'race_code']).sum('Voters').reset_index().pivot(index = ['county_nam', 'prec_id'], columns = 'race_code', values = 'Voters').reset_index()
total = precincts_long.groupby(['county_nam', 'prec_id']).sum('Voters').reset_index().rename(columns = { 'Voters' : 'ALL' })

precincts = pd.merge(precincts, party, on = ['county_nam', 'prec_id'])
precincts = pd.merge(precincts, race, on = ['county_nam', 'prec_id'])
precincts = pd.merge(precincts, total, on = ['county_nam', 'prec_id'])
precincts['NW'] = precincts['ALL'] - precincts['W']
precincts['uniqid'] = [i for i in range(precincts.shape[0])]

print(precincts.shape[0])

centroids = precincts.copy(); centroids.geometry = precincts.geometry.centroid
pw_centroids = pd.DataFrame()
pw_centroids['uniqid'] = centroids['uniqid'].repeat(centroids['ALL'])
pw_centroids['geometry'] = centroids['geometry'].repeat(centroids['ALL'])
pw_centroid_tree = cKDTree(np.array(list(pw_centroids.geometry.apply(lambda x: (x.x, x.y)))))

zctas = gpd.read_file(args.zctas).to_crs('ESRI:102003')
zctas = zctas[zctas['GISJOIN'].isin([l.strip() for l in open('NCRawData/NC_2022_ZCTAs.csv')])]

district_population = 200000

party_dissim = []; race_dissim = []
for _, zcta in tqdm(zctas.iterrows(), total = zctas.shape[0]):

    dist, idx = pw_centroid_tree.query((zcta.geometry.centroid.x, zcta.geometry.centroid.y), district_population)
    knn = list(dict.fromkeys(pd.DataFrame(pw_centroids.iloc[idx])['uniqid'].tolist()))
    knn_precincts = precincts[precincts['uniqid'].isin(knn)]
    
    print(knn_precincts.shape[0], sum(knn_precincts['ALL'].tolist()))

    party_spatial_index = segregation.singlegroup.SpatialDissim(knn_precincts, 'DEM', 'ALL')
    race_spatial_index = segregation.singlegroup.SpatialDissim(knn_precincts, 'NW', 'ALL')

    party_dissim.append(party_spatial_index.statistic)
    race_dissim.append(race_spatial_index.statistic)

zctas['party_dissim'] = party_dissim
zctas['race_dissim'] = race_dissim

zctas.to_file('ZCTA_seg_test.shp')
















