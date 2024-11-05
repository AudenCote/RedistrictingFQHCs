import os, sys
import geopandas as gpd
import pandas as pd
from tqdm import tqdm
import numpy as np
import argparse

parser = argparse.ArgumentParser('Calculate localized redistricting inequality statistics')
parser.add_argument('-g', '--gmetrics', type = str, help = 'Shapefile with gerrymandering metrics at the census block level')
parser.add_argument('-d', '--demographics', type = str, help = 'Block-level race/ethnicity population data')
parser.add_argument('-z', '--zctas', type = str, help = 'ZCTA-level shapefile')
parser.add_argument('-i', '--zcta_id', type = str, help = 'Variable to identify ZCTAs')
parser.add_argument('-o', '--output', type = str, help = 'Output file name')

args = parser.parse_args()

zctas = gpd.read_file(args.zctas).to_crs('ESRI:102003')

blocks = gpd.read_file(args.gmetrics)
#blocks = pd.merge(blocks, gpd.read_file(args.demographics).to_crs('ESRI:102003')[['GISJOIN', 'ALL', 'W', 'DEM', 'REP', 'DEM_B', 'REP_W']], on = 'GISJOIN')

block_overlap_by_zcta = pd.DataFrame(); count = 0
for index, zcta in tqdm(zctas.iterrows(), total=zctas.shape[0]):
    try:
        contained_blocks = blocks[blocks.geometry.within(zcta.geometry)]
        contained_blocks['overlap'] = 1
        
        overlap_blocks = blocks[blocks.geometry.intersects(zcta.geometry) & ~blocks.geometry.within(zcta.geometry)]
        overlaps = []
        for index, block in overlap_blocks.iterrows():
            block_prop_overlap = block.geometry.buffer(0).intersection(zcta.geometry.buffer(0)).area/block.geometry.area
            if block_prop_overlap > 0.01:
                if block_prop_overlap > 0.99:
                    overlaps.append(1)
                else:
                    overlaps.append(block_prop_overlap)
            else:
                block_overlaps.append(0)

        overlap_blocks['block_overlap'] = overlaps
        overlap_blocks = overlap_blocks[overlap_blocks['block_overlap'] > 0]

        zcta_blocks = pd.concat([contained_blocks, overlap_blocks])
        zcta_blocks[args.zcta_id] = zcta[args.zcta_id]
        zcta_blocks = zcta_blocks.drop(columns = ['geometry'])

        if count == 0:
            block_overlap_by_zcta = zcta_blocks
        else:
            block_overlap_by_zcta = pd.concat([block_overlap_by_zcta, zcta_blocks])
        
        count += 1
    except:
        print('One ZCTA failed for ' + args.zctas)

block_overlap_by_zcta['ALL'] = block_overlap_by_zcta['ALL'] * block_overlap_by_zcta['overlap']
block_overlap_by_zcta['dem_udm'] = block_overlap_by_zcta['dem_udm'] * block_overlap_by_zcta['ALL']
block_overlap_by_zcta['rep_udm'] = block_overlap_by_zcta['rep_udm'] * block_overlap_by_zcta['ALL']
block_overlap_by_zcta['nw_udm'] = block_overlap_by_zcta['nw_udm'] * block_overlap_by_zcta['ALL']

block_overlap_by_zcta['party_pd'] = (block_overlap_by_zcta['sld_dem']/(block_overlap_by_zcta['sld_dem'] + block_overlap_by_zcta['sld_rep']) - block_overlap_by_zcta['knn_dem']/(block_overlap_by_zcta['knn_dem'] + block_overlap_by_zcta['knn_rep'])) * block_overlap_by_zcta['ALL']
block_overlap_by_zcta['race_rd'] = (block_overlap_by_zcta['sld_nw']/block_overlap_by_zcta['sld_total'] - block_overlap_by_zcta['knn_nw']/block_overlap_by_zcta['knn_total']) * block_overlap_by_zcta['ALL']
block_overlap_by_zcta['race_opd'] = (block_overlap_by_zcta['sld_demb']/(block_overlap_by_zcta['sld_demb'] + block_overlap_by_zcta['sld_repw']) - block_overlap_by_zcta['knn_demb']/(block_overlap_by_zcta['knn_demb'] + block_overlap_by_zcta['knn_repw'])) * block_overlap_by_zcta['ALL']

block_overlap_by_zcta = block_overlap_by_zcta[[args.zcta_id, 'ALL', 'dem_udm', 'rep_udm', 'nw_udm', 'party_pd', 'race_rd', 'race_opd']]
block_overlap_by_zcta = block_overlap_by_zcta.groupby(args.zcta_id, as_index = False).sum()

block_overlap_by_zcta['dem_udm'] = block_overlap_by_zcta['dem_udm']/block_overlap_by_zcta['ALL']
block_overlap_by_zcta['rep_udm'] = block_overlap_by_zcta['rep_udm']/block_overlap_by_zcta['ALL']
block_overlap_by_zcta['nw_udm'] = block_overlap_by_zcta['nw_udm']/block_overlap_by_zcta['ALL']
block_overlap_by_zcta['party_pd'] = block_overlap_by_zcta['party_pd']/block_overlap_by_zcta['ALL']
block_overlap_by_zcta['race_rd'] = block_overlap_by_zcta['race_rd']/block_overlap_by_zcta['ALL']
block_overlap_by_zcta['race_opd'] = block_overlap_by_zcta['race_opd']/block_overlap_by_zcta['ALL']

zctas = pd.merge(zctas, block_overlap_by_zcta, on = args.zcta_id)

zctas.to_file(args.output)

