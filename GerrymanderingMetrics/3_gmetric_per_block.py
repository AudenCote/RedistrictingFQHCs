import os, sys
from tqdm import tqdm
import geopandas as gpd
import numpy as np
import pandas as pd
import geopandas as gpd
from scipy.spatial import cKDTree
import argparse

pd.set_option('display.max_columns', 500)

parser = argparse.ArgumentParser('Calculate localized redistricting inequality statistics')

parser.add_argument('-b', '--blocks', type = str, help = 'A shapefile of census blocks containing the number of voters in various demographic/party groups.')
parser.add_argument('-d', '--districts', type = str, help = 'A shapefile of legislative districts.')
parser.add_argument('--udm', action = 'store_true', help = 'Calculate UDM.')
parser.add_argument('--opd', action = 'store_true', help = 'Calculate opposed partisan dislocation.')
parser.add_argument('-gv', '--group_var', type = str, help = 'The variable (column name) in the blocks file corresponding to the number of voters of a specific target group.')
parser.add_argument('-ov', '--opposition_var', type = str, help = 'The variable (column name) in the blocks file corresponding to the number of voters in a specific "opposition" group.')
parser.add_argument('-tv', '--total_var', type = str, help = 'The variable (column name) in the blocks file corresponding to the total population.')
parser.add_argument('-r', '--entropy_radius', type = str, help = 'The radius in which to calculate uncertainty of district membership for the given group of voters.')
parser.add_argument('-o', '--output', type = str, help = 'Output file name and path')

args = parser.parse_args()

print('\nLoading shapefiles...\n')

blocks = gpd.read_file(args.blocks).to_crs('ESRI:102003')[['ALL', 'W', 'DEM', 'REP', 'DEM_B', 'REP_W', 'geometry', 'GISJOIN']]

sldls = gpd.read_file(args.districts).to_crs('ESRI:102003')

if 'district' in sldls.columns:
    sldls['DISTRICT'] = sldls['district']
elif 'DISTRICT_C' in sldls.columns:
    sldls['DISTRICT'] = sldls['DISTRICT_C']

print(args.districts)
print(sldls.columns)
print('\n\n')

print('\nAssigning blocks to districts...\n')

districts_block_indexed = { 'GISJOIN' : [], 'district' : [], 'propoverlap' : [], 'geometry' : [] }
for index, block in tqdm(blocks.iterrows(), total = blocks.shape[0]):
    block_districts = sldls[sldls.geometry.intersects(block.geometry)]
    
    for i2, dist in block_districts.iterrows():
        sect_geo = block.geometry.buffer(0).intersection(dist.geometry.buffer(0))
        prop_overlap = sect_geo.area/block.geometry.area
        districts_block_indexed['district'].append(dist['DISTRICT'])
        districts_block_indexed['GISJOIN'].append(block['GISJOIN'])
        districts_block_indexed['propoverlap'].append(prop_overlap)
        districts_block_indexed['geometry'].append(sect_geo)

#NOTE: Multiple rows per GISJOIN if a block falls into multiple districts
centroids = gpd.GeoDataFrame.from_dict(districts_block_indexed)
centroids = pd.merge(centroids, blocks.drop(columns = 'geometry'), on = 'GISJOIN')
centroids.geometry = centroids.geometry.centroid

centroids['ALL'] = centroids['ALL'] * centroids['propoverlap']
centroids['W'] = centroids['W'] * centroids['propoverlap']
centroids['DEM'] = centroids['DEM'] * centroids['propoverlap']
centroids['REP'] = centroids['REP'] * centroids['propoverlap']
centroids['DEM_B'] = centroids['DEM_B'] * centroids['propoverlap']
centroids['REP_W'] = centroids['REP_W'] * centroids['propoverlap']

print('\nCreating K-D tree...\n')

centroid_coordpairs = np.array(list(centroids.geometry.apply(lambda x: (x.x, x.y))))
centroid_tree = cKDTree(centroid_coordpairs)

udm_neighbor_data_blocks = []
if args.udm:
    print('\nFinding neighbors per block and calculating Uncertainty of District Membership...\n')
    
    for index, block in tqdm(blocks.iterrows(), total = blocks.shape[0]):
            radius_idxs = centroid_tree.query_ball_point((block.geometry.centroid.x, block.geometry.centroid.y), int(args.entropy_radius))
            radius_blocks = centroids.iloc[radius_idxs]

            radius_blocks = radius_blocks.fillna(0)
            #radius_blocks['distance'] = radius_blocks.geometry.distance(block.geometry.centroid)
           
            #Democrats
            d = [dist for i, dist in enumerate(radius_blocks['district'].tolist()) for f in range(int(radius_blocks['DEM'].tolist()[i]))]
            p = [d.count(dist)/len(d) for dist in list(dict.fromkeys(d))]
            e = -sum([pr * np.log2(pr) for pr in p])
            block['dem_udm'] = e

            #Republicans
            d = [dist for i, dist in enumerate(radius_blocks['district'].tolist()) for f in range(int(radius_blocks['REP'].tolist()[i]))]
            p = [d.count(dist)/len(d) for dist in list(dict.fromkeys(d))]
            e = -sum([pr * np.log2(pr) for pr in p])
            block['rep_udm'] = e

            #Non-White
            d = [dist for i, dist in enumerate(radius_blocks['district'].tolist()) for f in range(int(radius_blocks['ALL'].tolist()[i]) - int(radius_blocks['W'].tolist()[i]))]
            p = [d.count(dist)/len(d) for dist in list(dict.fromkeys(d))]
            e = -sum([pr * np.log2(pr) for pr in p])
            block['nw_udm'] = e

            udm_neighbor_data_blocks.append(block.to_dict())

    udm_neighbor_data_blocks = gpd.GeoDataFrame(udm_neighbor_data_blocks).drop(columns = 'geometry')

opd_neighbor_data_blocks = []
if args.opd:
    print('\nFinding neighbors per block and calculating Opposed Partisan Dislocation...\n')
    
    districts_for_counts = centroids['district'].tolist()
    blocks_per_district = { dist: districts_for_counts.count(dist) for dist in list(dict.fromkeys(districts_for_counts)) }

    pw_centroids = pd.DataFrame()
    pw_centroids['GISJOIN'] = centroids['GISJOIN'].repeat(centroids['ALL'])
    pw_centroids['geometry'] = centroids['geometry'].repeat(centroids['ALL'])
    pw_centroid_tree = cKDTree(np.array(list(pw_centroids.geometry.apply(lambda x: (x.x, x.y)))))

    for index, block in tqdm(centroids.iterrows(), total = centroids.shape[0]):
        try:
            district_total_pop, district_dem, district_rep, district_w, district_demb, district_repw = centroids[centroids['district'] == block['district']][['ALL', 'DEM', 'REP', 'W', 'DEM_B', 'REP_W']].sum().to_list()     

            dist, idx = pw_centroid_tree.query((block.geometry.x, block.geometry.y), district_total_pop)
            knn = list(dict.fromkeys(pd.DataFrame(pw_centroids.iloc[idx])['GISJOIN'].tolist()))
            knn_blocks = centroids[centroids['GISJOIN'].isin(knn)]
            
            #Partisan dislocation
            knn_total_pop, knn_dem, knn_rep = knn_blocks[['ALL', 'DEM', 'REP']].sum().to_list()
            block['knn_total'] = knn_total_pop
            block['knn_dem'] = knn_dem
            block['knn_rep'] = knn_rep
            block['sld_total'] = district_total_pop
            block['sld_dem'] = district_dem
            block['sld_rep'] = district_rep

            #Racial dislocation
            knn_w = knn_blocks[['W']].sum().to_list()[0]
            block['knn_nw'] = knn_total_pop - knn_w
            block['sld_nw'] = district_total_pop - district_w

            #Opposed party-race dislocation
            knn_demb, knn_repw = knn_blocks[['DEM_B', 'REP_W']].sum().tolist()
            block['knn_demb'] = knn_demb
            block['knn_repw'] = knn_repw
            block['sld_demb'] = district_demb
            block['sld_repw'] = district_repw

            opd_neighbor_data_blocks.append(block.to_dict())
        except Exception as e:
            print('OPD calculation failed for one block with error ' + str(e))

    opd_neighbor_data_blocks = pd.DataFrame(opd_neighbor_data_blocks)[['knn_total', 'knn_dem', 'knn_rep', 'sld_total', 'sld_dem', 'sld_rep', 'knn_nw', 'sld_nw', 'knn_demb', 'knn_repw', 'sld_demb', 'sld_repw', 'GISJOIN']]
    opd_neighbor_data_blocks = opd_neighbor_data_blocks.groupby('GISJOIN', as_index = False).mean()
    opd_neighbor_data_blocks = pd.merge(opd_neighbor_data_blocks, blocks.drop(columns = ['geometry']), on = 'GISJOIN')

if args.udm and args.opd:
    neighbor_data_blocks = pd.merge(udm_neighbor_data_blocks, opd_neighbor_data_blocks)
elif args.udm:
    neighbor_data_blocks = udm_neighbor_data_blocks
elif args.opd:
    neighbor_data_blocks = opd_neighbor_data_blocks

neighbor_data_blocks = pd.merge(neighbor_data_blocks, blocks[['GISJOIN', 'geometry']], on = 'GISJOIN')
neighbor_data_blocks = gpd.GeoDataFrame(neighbor_data_blocks)

neighbor_data_blocks.to_file(args.output)





