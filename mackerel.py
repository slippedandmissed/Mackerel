#!/usr/bin/python3.10

from dotenv import load_dotenv
from argparse import ArgumentParser
from tqdm.asyncio import tqdm
import functools
import itertools
import aiohttp
import asyncio
import pickle
import os

async def make_api_request(endpoint, params=None):
  url = 'https://api.tfl.gov.uk/' + endpoint
  params = {
      "app_id": os.getenv('TFL_API_APP_ID'),
      "app_key": os.getenv('TFL_API_KEY'),
      **(params or {})
    }
  response = None
  while response is None:
    async with aiohttp.ClientSession() as session:
      async with session.get(url, params=params) as response:
        response = await response.json()
    
    if "statusCode" in response and response["statusCode"] == 429:
      delay = int(response["message"].split("Try again in ")[1].split(" ")[0])
      print(f"Rate limited, waiting {delay} seconds")
      await asyncio.sleep(delay)
      response = None
  
  return response

def string_to_bit_field(string):
  bit_field = 0
  string = string.lower()
  for char in range(ord('a'), ord('z') + 1):
    if chr(char) in string:
      bit_field |= 1 << (char - ord('a'))
  return bit_field

class TubeStation:
  def __init__(self, station_id, name, bit_field):
    self.station_id = station_id
    self.name = name
    self.bit_field = bit_field
  
  def __repr__(self):
    return f"{self.name} (0x{self.bit_field:02x})"

class TubeStationAdjacency:
  def __init__(self, line, station_a_id, station_b_id):
    self.line = line
    self.station_a_id = station_a_id
    self.station_b_id = station_b_id

  def __repr__(self):
    return f"{self.station_a_id} <-{self.line}-> {self.station_b_id}"

class TubeGraph:
  def __init__(self, stations, adjacencies):
    self.stations = stations
    self.adjacencies = adjacencies

  def __repr__(self):
    return f"{self.stations}\n{self.adjacencies}"

async def get_tube_station(station_id):
  station = await make_api_request(f'StopPoint/{station_id}')
  station_name = station["commonName"].replace(" Underground Station", "")
  station_bit_field = string_to_bit_field(station_name)
  return (station_id, TubeStation(station_id, station_name, station_bit_field))

async def limit_concurrency(aws, concurrency_limit):
    aws = iter(aws)
    while True:
        batch = list(itertools.islice(aws, concurrency_limit))
        if not batch:
            break
        for result in await asyncio.gather(*batch):
            yield result

def map_unordered(func, iterable, *, concurrency_limit):
    aws = map(func, iterable)
    return limit_concurrency(aws, concurrency_limit)

async def get_all_tube_stations(adjacencies):
  tube_stations = {}

  async for station_id, tube_station in tqdm(map_unordered(get_tube_station, adjacencies.keys(), concurrency_limit=50), total=len(adjacencies)):
    tube_stations[station_id] = tube_station
  return tube_stations

async def get_all_tube_station_adjacencies():
  lines = await make_api_request('Line/Mode/tube')
  adjacencies = {}
  for line in lines:
    line_id = line["id"]
    line_stations = await make_api_request(f'Line/{line_id}/StopPoints')
    for i in range(len(line_stations) - 1):
      station_a_id = line_stations[i]["naptanId"]
      station_b_id = line_stations[i + 1]["naptanId"]
      line_name = line["name"]
      if station_a_id not in adjacencies:
        adjacencies[station_a_id] = {}
      adjacencies[station_a_id][station_b_id] = TubeStationAdjacency(line_name, station_a_id, station_b_id)
      # adjacencies[station_a_id][station_a_id] = TubeStationAdjacency(line_name, station_a_id, station_a_id)
      if station_b_id not in adjacencies:
        adjacencies[station_b_id] = {}
      adjacencies[station_b_id][station_a_id] = TubeStationAdjacency(line_name, station_b_id, station_a_id)
      # if station_a_id != station_b_id:
      #   adjacencies[station_b_id][station_b_id] = TubeStationAdjacency(line_name, station_b_id, station_b_id)
  
  return adjacencies

async def get_tube_graph():
  adjacencies = await get_all_tube_station_adjacencies()
  stations = await get_all_tube_stations(adjacencies)
  return TubeGraph(stations, adjacencies)

def filter_tube_graph(tube_graph, filter):
  stations = {}
  for station_id in tube_graph.stations:
    station = tube_graph.stations[station_id]
    if filter(station):
      stations[station_id] = station
  adjacencies = {}
  for station_a_id in stations:
    adjacencies[station_a_id] = {}
    for station_b_id, adjacency in tube_graph.adjacencies[station_a_id].items():
      if station_b_id in stations:
        adjacencies[station_a_id][station_b_id] = adjacency
  return TubeGraph(stations, adjacencies)

def longest_paths(adjacencies, path=None):
  path = path or []
  all_paths = [path]
  if len(path) == 0:
    for i in adjacencies.values():
      for adjacency in i.values():
        all_paths += longest_paths(adjacencies, [adjacency])
  else:
    last = path[-1]
    for nxt in adjacencies[last.station_b_id].values():
      if nxt not in path:
        all_paths += longest_paths(adjacencies, path + [nxt])
  max_length = max(map(len, all_paths))
  return list(filter(lambda x: len(x) == max_length, all_paths))


def banned_string_filter(banned_string, tube_station):
  return string_to_bit_field(banned_string) & tube_station.bit_field == 0

def print_journey(stations, journey):
  adj = None
  for adj in journey:
    print(stations[adj.station_a_id].name)
    print(f"  |\n  {adj.line}\n  ↓")
  if adj is not None:
    print(stations[adj.station_b_id].name)

if __name__ == "__main__":
  parser = ArgumentParser()
  parser.add_argument("word", help="Word to find longest tube journey for")
  parser.add_argument('-e', '--env', help='Environment to load', default='.env')
  parser.add_argument('--no-create-cache', help='Do not create a cached file of the tube data', action='store_true')
  parser.add_argument('--force', help='Do not use the cached file of the tube data, even if it exists', action='store_true')
  parser.add_argument('--cache-path', help='Path to the cached file of the tube data', default='tube_graph.pickle')
  args = parser.parse_args()

  print(f"Longest tube journeys (in terms of number of stops) avoiding all letters in \"{args.word}\":")
  
  load_dotenv(args.env)
  
  if args.force or not os.path.exists(args.cache_path):
    tube_graph = asyncio.run(get_tube_graph())
  else:
    with open(args.cache_path, 'rb') as f:
      tube_graph = pickle.load(f)

  if not args.no_create_cache:
    with open(args.cache_path, 'wb') as f:
      pickle.dump(tube_graph, f)

  filtered_graph = filter_tube_graph(tube_graph, functools.partial(banned_string_filter, args.word))
  longest_journeys = longest_paths(filtered_graph.adjacencies)

  
  if len(longest_journeys[0]) == 0:
    print("No journeys found")
  else:
    print(f"Found {len(longest_journeys)} journey{'' if len(longest_journeys) == 1 else 's'} of length {len(longest_journeys[0])+1}:\n")

    for journey in longest_journeys:
      print_journey(filtered_graph.stations, journey)
      print("\n--------------------\n")
  
  print("")

  if len(filtered_graph.stations) == 0:
    print("No stations found without these letters")
  else:
    print(f"Found {len(filtered_graph.stations)} station{'' if len(filtered_graph.stations) == 1 else 's'} without these letters:\n")

    for station in filtered_graph.stations.values():
      print(station.name)

