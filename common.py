from datetime import datetime
import json
from PIL import Image, ImageDraw

import requests, requests_cache
# requests_cache.install_cache('metro_cache')


class MetroNetwork:

    def __init__(self, api=None):
        self.api = api or MetroAPI()
        platforms = self.api.get_platforms()
        self.trains = {}
        self.stations = {name: MetroStation(self, name, code, platforms[code]) for code, name in self.api.get_stations().items()}
        for name, station in self.stations.items():
            for number, platform in station.platforms.items():
                platform.update()

    def add_train(self, platform, train_data):
        if train_data['trn'] in self.trains:
            train = self.trains[train_data['trn']]
            train.update(train_data, platform)
        else:
            train = MetroTrain(self, train_data, platform)
            self.trains[train.id] = train
        return train.arrival(platform)

    def print_map(self):
        map = MetroMap()
        # for num, train in self.trains.items():
        #     print(train)
        # for code, station in self.stations.items():
        #     for number, platform in station.platforms.items():
        #         if platform.x != 0 and platform.y != 0:
        #             map.add_train(code, (platform.x, platform.y), platform.d)
        for number, train in self.trains.items():
            map.add_train(number, (train.x, train.y), train.d, train.colour)
        map.save()

    def __repr__(self):
        return '\n\n'.join(f'{station}' for station in self.stations.values())


class MetroStation:
    
    def __init__(self, network, name, code, platforms=None):
        self.network, self.name, self.code = network, name, code
        self.platforms = {}
        if platforms is not None:
            for platform in platforms:
                self.add_platform(platform)
    
    def add_platform(self, data):
        p = MetroPlatform(self, data)
        self.platforms[p.number] = p
    
    def __repr__(self):
        return f'{self.name} ({self.code})\n' + '\n'.join(f'{platform}' for platform in self.platforms.values())


class MetroPlatform:

    def __init__(self, station, data):
        self.station = station
        self.number = str(data.get('platformNumber', '???'))
        self.direction = data.get('direction', '???')
        self.text = data.get('helperText', '???')
        coords = data.get('coordinates', {'longitude': -1.64502501487732, "latitude": 55.0135612487793})
        self.lat = coords.get('latitude', '0')
        self.lon = coords.get('longitude', '0')
        self.x = coords.get('x', '0')
        self.y = coords.get('y', '0')
        self.d = coords.get('d', '0')
        self.arrivals = []

    def update(self):
        train_datas = self.station.network.api.get_times(self.station.code, self.number)
        for train_data in train_datas:
            self.arrivals.append(self.station.network.add_train(self, train_data))
    
    def __repr__(self):
        return f'{self.station.name}, Platform {self.number}'#
        return f'    Platform {self.number}, {self.text}\n' + '\n'.join(f'        Train {train.id} in {arrival['dueIn']} mins ({arrival['actualPredictedTime']})' for train, arrival in self.arrivals)


class MetroTrain:
    
    OFFSETS = {
        'READY_TO_START': {
            'N': (0, 0),
            'S': (0, 0),
            'E': (0, 0),
            'W': (0, 0),
            'U': (0, 0),
            'D': (0, 0),
        },
        'APPROACHING': {
            'N': (0, 20),
            'S': (0, -20),
            'E': (-20, 0),
            'W': (20, 0),
            'U': (9, 15),
            'D': (-7, -15),
        },
        'ARRIVED': {
            'N': (0, 0),
            'S': (0, 0),
            'E': (0, 0),
            'W': (0, 0),
            'U': (0, 0),
            'D': (0, 0),
        },
        'DEPARTED': {
            'N': (0, -20),
            'S': (0, 20),
            'E': (20, 0),
            'W': (-20, 0),
            'U': (-7, -15),
            'D': (9, 15),
        },
    }

    def __init__(self, network, train_data, platform):
        self.network = network
        self.id = train_data.get('trn', '???')
        self.colour = 'red'
        if self.id == '121':
            self.colour = 'blue'
        self.destination = train_data.get('destination', '???')
        self.line = train_data.get('line', '???')
        self.event = []
        self.arrivals = {}
        self.position = None
        self.update(train_data, platform)

    def update(self, train_data, platform):
        self.event = {
            'lastEvent': train_data['lastEvent'],
            'lastEventLocation': train_data['lastEventLocation'],
            'lastEventTime': train_data['lastEventTime'],
        }
        self.arrivals[(platform.station, platform.number)] = {
            'station': platform.station,
            'platform': platform.number,
            'dueIn': train_data['dueIn'],
            'actualPredictedTime': datetime.fromisoformat(train_data['actualPredictedTime']),
        }
        station, platform = train_data['lastEventLocation'][:-11], train_data['lastEventLocation'][-1]
        if station == 'Monument':
            if platform in ('3', '4'):
                station = 'Monument W-E'
            else:
                station = 'Monument N-S'
        try:
            self.position = (self.event['lastEvent'], self.network.stations[station].platforms[platform])
        except KeyError as e:
            print(station)
            print(platform)
            raise e

    @property
    def x(self):
        return self.position[1].x + self.OFFSETS[self.position[0]][self.d][0]

    @property
    def y(self):
        return self.position[1].y + self.OFFSETS[self.position[0]][self.d][1]

    @property
    def d(self):
        return self.position[1].d

    def arrival(self, platform):
        return self, self.arrivals[(platform.station, platform.number)]

    def __repr__(self):
        return f'Train {self.id}, {self.line} line towards {self.destination}, last reported {self.position[0]} {self.position[1]}'
    

class MetroMap:

    OFFSETS = {
        'N': [(0, 10), (0, -10), (-5, -5), (5, -5), (-24, 0)],
        'S': [(0, -10), (0, 10), (-5, 5), (5, 5), (8, 0)],
        'E': [(-10, 0), (10, 0), (5, 5), (5, -5), (-16, -12)],
        'W': [(10, 0), (-10, 0), (-5, 5), (-5, -5), (0, 5)],
        'U': [(5, 8), (-6, -9), (-6, -1), (0, -5), (-8, 8)],
        'D': [(-6, -9), (5, 8), (6, 1), (0, 5), (8, 8)],
    }

    def __init__(self):
        self.trains = []

    def add_train(self, name, position, direction, colour='red'):
        self.trains.append({
            'name': name,
            'position': position,
            'direction': direction,
            'colour': colour,
        })

    def arrow_parts(self, position, os):
        parts = []
        parts.append(((position[0] + os[0][0], position[1] + os[0][1]), (position[0] + os[1][0], position[1] + os[1][1])))
        parts.append(((position[0] + os[1][0], position[1] + os[1][1]), (position[0] + os[2][0], position[1] + os[2][1])))
        parts.append(((position[0] + os[1][0], position[1] + os[1][1]), (position[0] + os[3][0], position[1] + os[3][1])))
        return parts

    def save(self):
        with Image.open('map.png') as im:
            draw = ImageDraw.Draw(im)
            for train in self.trains:
                os = self.OFFSETS[train['direction']]
                for f, t in self.arrow_parts(train['position'], os):
                    draw.line([f, t], fill=train['colour'], width=4)
                draw.text((train['position'][0] + os[4][0], train['position'][1] + os[4][1]), train['name'], fill=train['colour'])
            im.save('map-annoted.png')
        

class MetroAPI:

    API_BASE = 'https://metro-rti.nexus.org.uk/api/'

    def __init__(self):
        pass

    def get_json(self, path):
        r = requests.get(f'{self.API_BASE}{path}')
        return r.json()

    def get_times(self, station_code, platform_number):
        return self.get_json(f'times/{station_code}/{platform_number}')

    def get_stations(self):
        with open('stations.json', 'r') as f:
            return json.load(f)
        # return self.get_json('stations')

    def get_platforms(self):
        with open('platforms.json', 'r') as f:
            return json.load(f)
        # return self.get_json('stations/platforms')


def main():
    m = MetroNetwork()
    m.print_map()
    
if __name__ == '__main__':
    main()