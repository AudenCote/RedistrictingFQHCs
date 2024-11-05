import os, sys
import pandas as pd
import argparse
import chardet

pd.set_option('display.max_columns', 500)
pd.set_option('display.max_rows', 10000)

parser = argparse.ArgumentParser()

parser.add_argument('-v', '--voters', help = 'Individual voter registration records')
parser.add_argument('-o', '--output', help = 'Output file name')

args = parser.parse_args()

def decode():
    failed = 0; total = 0
    with open('NCRawData/vr/VR_20061020_encodingconvert.txt', 'w') as o:
        for i, line in enumerate(open('NCRawData/vr/VR_20061020.txt', 'rb')):
            #print(chardet.detect(line))
            
            total += 1
            try:
                o.write(line.decode())
                #print(line.decode() + '\n')
            except:
                try:    
                    o.write(line.decode(encoding = 'UTF-16LE'))
                except:
                    try:
                        o.write(line.decode(encoding = 'ascii'))
                    except:
                        failed += 1
                        print('Skipping line ' + str(i) + '\n')

    print(str(failed) + ' lines failed total (' + str(failed/total) + '%).')


def precinct(args):
        
    #vr = pd.read_csv(args.voters, encoding = 'UTF-16LE', compression = 'zip', sep = '\t', on_bad_lines='warn', engine = 'python')
    vr = pd.read_csv('NCRawData/vr/VR_20061020_encodingconvert.txt', sep = '\t', on_bad_lines='warn', engine = 'python')

    vr = vr[(vr['status_cd'].str.strip() == 'A') & (vr['reason_cd'].str.strip() == 'AV')]
    
    vr['party_cd'] = vr['party_cd'].astype(str).map(lambda x : x.strip() if x.strip() in ['DEM', 'REP', 'UNA'] else 'OP')
    vr['race_code'] = vr['race_code'].astype(str).map(lambda x : x.strip() if x.strip() in ['B', 'W', 'U'] else 'OR')

    vr = vr.groupby(['county_desc', 'precinct_abbrv', 'party_cd', 'race_code', 'ethnic_code']).size().reset_index(name='Voters')

    vr.to_csv(args.output)


def zcta(args):
    
    #vr = pd.read_csv(args.voters, encoding = 'UTF-16LE', compression = 'zip', sep = '\t', on_bad_lines='warn', engine = 'python')
    vr = pd.read_csv('NCRawData/vr/VR_20061020_encodingconvert.txt', sep = '\t', on_bad_lines='warn', engine = 'python')

    vr = vr[(vr['status_cd'].str.strip() == 'A') & (vr['reason_cd'].str.strip() == 'AV')]

    vr['party_cd'] = vr['party_cd'].astype(str).map(lambda x : x.strip() if x.strip() in ['DEM', 'REP', 'UNA'] else 'OP')
    vr['race_code'] = vr['race_code'].astype(str).map(lambda x : x.strip() if x.strip() in ['B', 'W', 'U'] else 'OR')

    vr = vr.groupby(['zip_code', 'party_cd', 'race_code', 'ethnic_code']).size().reset_index(name='Voters')

    vr.to_csv(args.output)



#decode()
#precinct(args)
zcta(args)


