import os, sys
import geopandas as gpd
import pandas as pd
from tqdm import tqdm
import argparse
from statistics import mean
import matplotlib.pyplot as plt
from scipy.spatial import cKDTree
import numpy as np
from pointpats import PoissonPointProcess, PoissonClusterPointProcess, Window, poly_from_bbox, PointPattern
import libpysal as ps
from libpysal.cg import shapely_ext

import warnings
warnings.filterwarnings("ignore")

pd.set_option('display.max_columns', 500)
pd.set_option('display.max_rows', 10000)

voters_per_district = 1000
n_neighbors = 25

iterations = 100

blue = '#0000FF'
red = '#FF0000'

sldus = gpd.read_file(sys.argv[1]).to_crs('ESRI:102003')

threshes = [0, 0.05, 0.1, 0.15, 0.2]

pds = { thresh : [] for thresh in threshes }; udms = { thresh : [] for thresh in threshes }; party_maxps = { thresh : [] for thresh in threshes }
for change_mind_threshold in threshes:

	print('\n\n===================\n\nTHRESHOLD: ' + str(change_mind_threshold) + '\n\n===================\n\n')

	for i in tqdm(range(iterations)):

		print('Generating voters...')

		voters = gpd.GeoDataFrame()
		#for _, sldu in tqdm(sldus.iterrows(), total = sldus.shape[0]):
		for _, sldu in sldus.iterrows():
			sldu_gdf = gpd.GeoDataFrame(geometry = gpd.GeoSeries(sldu.geometry))
			x_min, y_min, x_max, y_max = sldu_gdf.total_bounds

			x = np.random.uniform(x_min, x_max, voters_per_district)
			y = np.random.uniform(y_min, y_max, voters_per_district)

			district_voters = gpd.GeoSeries(gpd.points_from_xy(x, y))
			district_voters = district_voters[district_voters.within(sldu_gdf.unary_union)]
			district_voters =  gpd.GeoDataFrame(geometry = district_voters)
			district_voters['DISTRICT'] = sldu['DISTRICT']
			voters = pd.concat([voters, district_voters])

		print('Assigning party...')

		#Every one makes a random decision
		voters['party'] = np.random.choice([red, blue], voters.shape[0])
		voters_tree = cKDTree(np.array(list(voters.geometry.apply(lambda x: (x.x, x.y)))))
		voters = voters.sample(frac=1).reset_index(drop=True)

		#Now they start changing their minds based on what their neighbors think
		#for idx, voter in tqdm(voters.iterrows(), total = voters.shape[0]):
		for idx, voter in voters.iterrows():
			_, voter_idxs = voters_tree.query((voter.geometry.x, voter.geometry.y), n_neighbors)
			nearest_voters = voters.iloc[voter_idxs]

			prop_blue = nearest_voters[nearest_voters['party'] == blue].shape[0]/n_neighbors

			if prop_blue > 0.5 + change_mind_threshold:
				voters.loc[idx, 'party'] = blue
			elif prop_blue < 0.5 - change_mind_threshold:
				voters.loc[idx, 'party'] = red

		print('Calculating partisan dislocation...')

		pd_ = []
		#for _, voter in tqdm(voters.iterrows(), total = voters.shape[0]):
		for _, voter in voters.iterrows():

			district_voters = voters[voters['DISTRICT'] == voter['DISTRICT']]

			district_prop_blue = district_voters[district_voters['party'] == blue].shape[0]/district_voters.shape[0]

			_, voter_idxs = voters_tree.query((voter.geometry.x, voter.geometry.y), district_voters.shape[0])
			nearest_voters = voters.iloc[voter_idxs]

			nearest_prop_blue = nearest_voters[nearest_voters['party'] == blue].shape[0]/district_voters.shape[0]

			pd_.append(abs(district_prop_blue - nearest_prop_blue))

		pds[change_mind_threshold].append(mean(pd_))

		print('Calculating uncertainty of district membership...')

		udm = []; party_maxp = []
		for _, voter in voters.iterrows():
		    voter_idxs = voters_tree.query_ball_point((voter.geometry.x, voter.geometry.y), 5000)
		    nearest_voters = voters.iloc[voter_idxs]

		    districts = [nearest_voters.iloc[i]['DISTRICT'] for i in range(nearest_voters.shape[0]) if nearest_voters.iloc[i]['party'] == voter['party']]
		    dists_p = [districts.count(dist)/len(districts) for dist in list(dict.fromkeys(districts))]
		    dists_e = -sum([pr * np.log2(pr) for pr in dists_p])
		    udm.append(dists_e)

		    parties = nearest_voters['party'].tolist()
		    parties_p = [parties.count(p)/len(parties) for p in list(dict.fromkeys(parties))]
		    party_maxp.append(max(parties_p))

		udms[change_mind_threshold].append(mean(udm))

		party_maxps[change_mind_threshold].append(mean(party_maxp))

with open('MetricsByThreshold.csv', 'w') as o:
	o.write('Threshold,Metric,Value\n')

	for thresh in threshes:

		for pd_ in pds[thresh]:
			o.write(str(thresh) + ',PD,' + str(pd_) + '\n')

		for udm in udms[thresh]:
			o.write(str(thresh) + ',UDM,' + str(udm) + '\n')

		for pmp in party_maxps[thresh]:
			o.write(str(thresh) + ',PMP,' + str(pmp) + '\n')
		

		


