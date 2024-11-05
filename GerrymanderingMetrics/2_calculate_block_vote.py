import os, sys
from tqdm import tqdm
import geopandas as gpd
import numpy as np
import pandas as pd
import geopandas as gpd
import shapely
from scipy.spatial import cKDTree
import argparse

import warnings
warnings.filterwarnings("ignore")

pd.set_option('display.max_columns', 500)
pd.set_option('display.max_rows', 10000)

parser = argparse.ArgumentParser()

parser.add_argument('-v', '--voters', help = 'Precinct-level vote results (csv)')
parser.add_argument('-p', '--precincts', help = 'Precincts shapefile')
parser.add_argument('-i', '--impute', action = 'store_true', help = 'Impute vote data from missing precincts using neighboring precincts')
parser.add_argument('-b', '--blocks', help = 'Blocks shapefile')
parser.add_argument('-d', '--demographics', help = 'Block-level demographic variables (csv)')
parser.add_argument('-o', '--output', help = 'Output file name')

args = parser.parse_args()

precinct_vr_raw = pd.read_csv(args.voters)
precinct_vr_raw['precinct_abbrv'] = ['0'*(6-len(str(pid).strip())) + str(pid).strip() for pid in precinct_vr_raw['precinct_abbrv']]

precinct_vr_r = precinct_vr_raw.groupby(['county_desc', 'precinct_abbrv', 'race_code', 'party_cd'], as_index = False).sum().rename(columns = { 'race_code' : 're_code'})
precinct_vr_e = precinct_vr_raw.groupby(['county_desc', 'precinct_abbrv', 'ethnic_code', 'party_cd'], as_index = False).sum().rename(columns = { 'ethnic_code' : 're_code'})
precinct_vr_a = precinct_vr_raw.groupby(['county_desc', 'precinct_abbrv', 'party_cd'], as_index = False).sum()
precinct_vr_a['re_code'] = 'ALL'

precinct_vr = pd.concat([precinct_vr_r, precinct_vr_e, precinct_vr_a])

print(precinct_vr.head(30))

precinct_shp = gpd.read_file(args.precincts).to_crs('ESRI:102003')
precinct_shp.columns = [x.lower() for x in precinct_shp.columns]
if 'seims_code' in precinct_shp.columns:
    precinct_shp['prec_id'] = precinct_shp['seims_code']
    precinct_shp['county_nam'] = precinct_shp['county'].str.upper()
precinct_shp = precinct_shp[['prec_id', 'county_nam', 'geometry']]
precinct_shp['prec_id'] = ['0'*(6-len(str(pid).strip())) + str(pid).strip() for pid in precinct_shp['prec_id']]

shared = [i for i in precinct_shp['prec_id'].tolist() if i in precinct_vr_raw['precinct_abbrv'].tolist()]

block_pop = pd.read_csv(args.demographics)[['GISJOIN', 'NL_W', 'NL_B', 'NL_O', 'HL_W', 'HL_B', 'HL_O']]
block_pop['ALL'] = block_pop['NL_W'] + block_pop['NL_B'] + block_pop['NL_O'] + block_pop['HL_W'] + block_pop['HL_B'] + block_pop['HL_O']
block_pop['B'] = block_pop['NL_B'] + block_pop['HL_B']
block_pop['W'] = block_pop['NL_W'] + block_pop['HL_W']
block_pop['HL'] = block_pop['HL_W'] + block_pop['HL_B'] + block_pop['HL_O']
block_pop['NL'] = block_pop['NL_W'] + block_pop['NL_B'] + block_pop['NL_O']
block_pop = block_pop[['GISJOIN', 'ALL', 'HL', 'NL', 'B', 'W']]
block_pop = pd.melt(block_pop, id_vars = ['GISJOIN'])
block_pop = block_pop.rename(columns = { 'variable' : 're_code', 'value' : 'Population' })

block_shp_raw = gpd.read_file(args.blocks).to_crs('ESRI:102003')
block_shp_raw = block_shp_raw[['GISJOIN', 'geometry']]

block_shp = pd.merge(block_shp_raw, block_pop, on = 'GISJOIN')

def final_process_contained_blocks(contained_blocks):

    contained_blocks['Voters'] = contained_blocks['PropVote'] * contained_blocks['Population']
    contained_blocks['Voters'] = contained_blocks['Voters'].map(lambda x : int(round(x)))
    contained_blocks['pre_code'] = contained_blocks['party_cd'] + '_' + contained_blocks['re_code']

    contained_blocks_p = pd.pivot_table(contained_blocks[contained_blocks['re_code'] == 'ALL'][['GISJOIN', 'party_cd', 'Voters']].groupby(['GISJOIN', 'party_cd'], as_index = False).sum(), index = ['GISJOIN'], columns = ['party_cd'])
    contained_blocks_re = pd.pivot_table(contained_blocks[['GISJOIN', 're_code', 'Population']].groupby(['GISJOIN', 're_code'], as_index = False).first(), index = ['GISJOIN'], columns = ['re_code'])
    contained_blocks_v = pd.pivot_table(contained_blocks[['GISJOIN', 'pre_code', 'Voters']].groupby(['GISJOIN', 'pre_code'], as_index = False).sum(), index = ['GISJOIN'], columns = ['pre_code'])

    contained_blocks = pd.merge(pd.merge(contained_blocks_re, contained_blocks_v, on = 'GISJOIN'), contained_blocks_p, on = 'GISJOIN').droplevel(0, axis=1).rename_axis(None, axis=1).reset_index()
    
    contained_blocks = contained_blocks.fillna(0)

    return contained_blocks

blocks_with_stats = pd.DataFrame()
count = 0; missing_precincts = []; prop_vote_precincts = []
for index, precinct in tqdm(precinct_shp.iterrows(), total=precinct_shp.shape[0]):
    
    contained_blocks = block_shp[block_shp.geometry.within(precinct.geometry)]

    contained_blocks['Overlap'] = 1

    overlap_blocks = block_shp[block_shp.geometry.intersects(precinct.geometry) & ~block_shp.geometry.within(precinct.geometry)]

    overlaps = []
    for index, block in overlap_blocks.iterrows():
        overlaps.append(block.geometry.buffer(0).intersection(precinct.geometry.buffer(0)).area/block.geometry.area)

    overlap_blocks['Overlap'] = overlaps
    overlap_blocks['Overlap'] = overlap_blocks['Overlap'].map(lambda x : 0 if x < 0.01 else (1 if x > 0.99 else x))
    overlap_blocks = overlap_blocks[overlap_blocks['Overlap'] > 0]

    contained_blocks = pd.concat([contained_blocks, overlap_blocks])

    contained_blocks['Population'] = contained_blocks['Population'] * contained_blocks['Overlap']
    
    current_precinct_vr = precinct_vr[(precinct_vr['county_desc'] == precinct['county_nam']) & (precinct_vr['precinct_abbrv'] == precinct['prec_id'])]
   
    if current_precinct_vr.shape[0] == 0:
        contained_blocks_missing = contained_blocks
        contained_blocks_missing['prec_id'] = precinct['prec_id']
        missing_precincts.append(contained_blocks)

    contained_blocks = contained_blocks.drop(columns = ['Overlap', 'geometry'])

    precinct_total_population = contained_blocks.groupby('re_code', as_index = False).sum()
    
    current_precinct_vr = pd.merge(current_precinct_vr, precinct_total_population, on = ['re_code'])
    current_precinct_vr['PropVote'] = current_precinct_vr['Voters']/current_precinct_vr['Population'].map(lambda x : max(1, x))
    
    prop_vote_precincts.append(current_precinct_vr[['county_desc', 'precinct_abbrv', 're_code', 'party_cd', 'Voters', 'Population']])
    current_precinct_vr = current_precinct_vr[['re_code', 'party_cd', 'PropVote']]
   
    contained_blocks = pd.merge(contained_blocks, current_precinct_vr, on = ['re_code'])

    contained_blocks = final_process_contained_blocks(contained_blocks)
    
    if count == 0:
        blocks_with_stats = contained_blocks
    else:
        blocks_with_stats = pd.concat([blocks_with_stats, contained_blocks])

    count += 1


#IMPUTING NOT YET THOROUGHLY TESTED, AND NOT APPLIED IN PRELIMINARY WORK
imputed_gisjoins = []
if args.impute:
    for precinct in missing_precincts:
        precinct_geo = precinct[['geometry']].dissolve()

        nearest_precincts = [(p['county_desc'], p['precinct_abbrv']) for _,p in precinct_shp[precinct_shp.geometry.touches(precinct.geometry)].iterrows()]
        nearest_precincts_prop_vote = [p for p in prop_vote_precincts if (p['county_desc'], p['precinct_abbrv']) in nearest_precincts]

        if len(nearest_precincts_prop_vote) == 0:
            print('\nWARNING: Missing voter registration data for precinct and it could not be imputed from adjacent precincts.\n')
            continue
        else:
            nearest_precincts_prop_vote = pd.concat(nearest_precincts_prop_vote)
            nearest_precincts_prop_vote = nearest_precincts_prop_vote[['re_code', 'party_cd', 'Voters', 'Population']]
            current_precinct_vr = nearest_precincts_prop_vote.groupby(['re_code', 'party_code'], as_index = False).sum()
            current_precinct_vr['PropVote'] = current_precinct_vr['Voters']/current_precinct_vr['Population'].map(lambda x : max(1, x))
            current_precinct_vr = current_precinct_vr[['re_code', 'party_cd', 'PropVote']]

            precinct = precinct.drop(columns = ['Overlap', 'geometry'])
            contained_blocks = pd.merge(precinct, current_precinct_vr, on = 're_code')
            contained_blocks = final_process_contained_blocks(contained_blocks)
            imputed_gisjoins.extend(contained_blocks['GISJOIN']).tolist()

            blocks_with_stats = pd.concat([blocks_with_stats, contained_blocks])
        

blocks_with_stats = blocks_with_stats.groupby('GISJOIN', as_index = False).sum()
blocks_with_stats['imputed'] = blocks_with_stats['GISJOIN'].map(lambda x : True if x in imputed_gisjoins else False)
blocks_with_stats = gpd.GeoDataFrame(pd.merge(blocks_with_stats, block_shp_raw, on = 'GISJOIN'))
blocks_with_stats.to_file(args.output)


