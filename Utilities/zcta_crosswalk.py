import os, sys
from tqdm import tqdm
import pandas as pd
import geopandas as gpd
import argparse

import warnings
warnings.filterwarnings("ignore")

pd.set_option('display.max_columns', 500)
pd.set_option('display.max_rows', 10000)

parser = argparse.ArgumentParser()

parser.add_argument('-z', '--zctas', type = str, help = '"Sample year" ZCTA shapefile')
parser.add_argument('-r', '--reference', type = str, help = '2022 ZCTA shapefile')
parser.add_argument('-b', '--blocks', type = str, help = 'Census block shapefile')
parser.add_argument('-d', '--demographics', type = str, help = 'Census block popuation data')
parser.add_argument('-o', '--output', type = str, help = 'Output file name')

args = parser.parse_args()

block_pop = pd.read_csv(args.demographics)[['GISJOIN', 'NL_W', 'NL_B', 'NL_O', 'HL_W', 'HL_B', 'HL_O']]
block_pop['ALL'] = block_pop['NL_W'] + block_pop['NL_B'] + block_pop['NL_O'] + block_pop['HL_W'] + block_pop['HL_B'] + block_pop['HL_O']
block_pop = block_pop[['GISJOIN', 'ALL']]

block_shp_raw = gpd.read_file(args.blocks).to_crs('ESRI:102003')
block_shp_raw = block_shp_raw[['GISJOIN', 'geometry']]

block_shp = pd.merge(block_shp_raw, block_pop, on = 'GISJOIN')

nc_state = gpd.read_file('NCRawData/sldu_shapefiles/sldu_shapefile_2020-2024.zip').to_crs('ESRI:102003')[['ST', 'geometry']].dissolve(by = 'ST')
nc_state = nc_state.reset_index()

zctas = gpd.read_file(args.zctas).to_crs('ESRI:102003')
zctas = zctas.sjoin(nc_state, how = 'inner', predicate = 'intersects')

if 'GISJOIN' not in zctas.columns:
    zctas.columns = [x.lower() for x in zctas.columns]
    if 'prec_id' in zctas.columns:
        zctas['GISJOIN'] = zctas['prec_id']
    elif 'seims_code' in zctas.columns:
        zctas['GISJOIN'] = zctas['seims_code']

ref = gpd.read_file(args.reference).to_crs('ESRI:102003')
ref = ref.sjoin(nc_state, how = 'inner', predicate = 'intersects')

if 'GISJOIN' not in ref.columns:
    ref['GISJOIN'] = ref['DISTRICT']

overlap_outfile = open('Output/zcta_crosswalk/' + args.output, 'w')
overlap_outfile.write('ZCTA,Ref,OverlapPop\n')

for _, zcta in tqdm(zctas.iterrows(), total = zctas.shape[0]):
    for _, ref_unit in ref.iterrows():
        overlap = zcta.geometry.buffer(0).intersection(ref_unit.geometry.buffer(0))
        
        if overlap.area/zcta.geometry.area >= 0.01:

            contained_blocks = block_shp[block_shp.geometry.within(overlap)]
            overlap_blocks = block_shp[block_shp.geometry.intersects(overlap) & ~block_shp.geometry.within(overlap)]

            overlaps = []
            for index, block in overlap_blocks.iterrows():
                try:
                    overlaps.append(block.geometry.buffer(0).intersection(overlap.buffer(0)).area/block.geometry.area)
                except Exception as e:
                    print('\nUnable to count census block ' + block['GISJOIN'] + ' due to: ' + str(e) + '\n')
                    overlaps.append(0)

            overlap_blocks['overlap'] = overlaps
            overlap_blocks['overlap'] = overlap_blocks['overlap'].map(lambda x : 0 if x < 0.01 else (1 if x > 0.99 else x))
            overlap_blocks = overlap_blocks[overlap_blocks['overlap'] > 0]
            contained_blocks['overlap'] = 1

            contained_blocks = pd.concat([contained_blocks, overlap_blocks])

            contained_blocks['PW_ALL'] = contained_blocks['ALL'] * contained_blocks['overlap']

            total_overlap_pop = sum(contained_blocks['PW_ALL'].tolist())
            
            overlap_outfile.write(zcta['GISJOIN'] + ',' + ref_unit['GISJOIN'] + ',' + str(total_overlap_pop) + '\n')



