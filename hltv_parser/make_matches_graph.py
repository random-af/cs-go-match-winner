import requests
import bs4 as bs
import csv
import asyncio
import itertools
from proxybroker import Broker
from datetime import datetime
import time


class MakeMatchesGraph:

    def __init__(self, start_date=None, end_date=None, min_lineup_match=5, from_state=None):
        self.session = requests.Session()
        self.session.headers = {
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_5) AppleWebKit/537.36 (KHTML, like Gecko) \
                            Chrome/79.0.3945.130 Safari/537.36'}
        self.lineups = set()
        self.lineups_info = {}
        self.matches = {}
        self.new_lineups = None
        self.new_matches = None
        self.old_matches = None
        self.start_date = start_date
        if end_date is not None:
            self.end_date = end_date
        else:
            self.end_date = datetime.today().strftime('%Y-%m-%d')
        self.min_lineup_match = min_lineup_match
        self.proxies_iter = self.make_proxies_iter()
        self.curr_proxy = next(self.proxies_iter)
        self.from_state = from_state
        self.counter = 0

    def make_proxies_iter(self):
        proxies = asyncio.Queue()
        broker = Broker(proxies)
        tasks = asyncio.gather(
            broker.find(types=['HTTPS'], limit=10),
            self.get_proxies(proxies))
        loop = asyncio.get_event_loop()
        print('finding proxies')
        result = loop.run_until_complete(tasks)
        return iter(result[1])

    async def get_proxies(self, proxies):
        proxies_list = []
        while True:
            proxy = await proxies.get()
            if proxy is None:
                break
            proxies_list.append('%s:%d' % (proxy.host, proxy.port))
            print('%s:%d' % (proxy.host, proxy.port))
        return [None,] + proxies_list

    def save_state(self):
        with open('f.txt', 'w') as f:
            f.write('lineups\n')
            for lineup in self.lineups:
                f.write(self.encode_lineup(lineup) + '\n')
            f.write('lineups_info\n')
            for lineup in self.lineups_info:
                f.write('self.lineups_info[{}] = {}\n'.format(lineup, self.lineups_info[lineup]))
            f.write('matches\n')
            for match_id in self.matches:
                f.write('self.matches[{}] = {}\n'.format(match_id, self.matches[match_id]))
            f.write('new_lineups\n')
            for new_lineup in self.new_lineups:
                f.write(self.encode_lineup(new_lineup) + '\n')
            f.write('new_matches\n')
            for match_id in self.new_matches:
                f.write(match_id + '\n')
            f.write('old_matches\n')
            for match_id in self.old_matches:
                f.write(match_id + '\n')
            if self.start_date is not None:
                f.write('start date\n')
                f.write(self.start_date + '\n')
            if self.end_date is not None:
                f.write('end date\n')
                f.write(self.end_date + '\n')
            f.write('min lineup match\n')
            f.write(str(self.min_lineup_match) + '\n')

    def load_state(self, file_name):
        self.new_lineups = set()
        self.old_matches = set()
        self.new_matches = set()
        with open(file_name, 'r') as f:
            lines = f.readlines()
            for line in lines:
                line = line.strip()
                if line in ('lineups', 'lineups_info', 'matches', 'new_lineups', 'new_matches', 'old_matches', 'start date',
                            'end date', 'min lineup match'):
                    what_reading = line
                    continue
                if what_reading == 'lineups':
                    self.lineups.add(line)
                elif what_reading == 'lineups_info':
                    exec(line)
                elif what_reading == 'matches':
                    exec(line)
                elif what_reading == 'new_lineups':
                    self.new_lineups.add(line)
                elif what_reading == 'new_matches':
                    self.new_matches.add(line)
                elif what_reading == 'old_matches':
                    self.old_matches.add(line)
                elif what_reading == 'start date':
                    self.start_date = line
                elif what_reading == 'end date':
                    self.end_date = line
                elif what_reading == 'min lineup match':
                    self.min_lineup_match = int(line)

    def encode_lineup(self, lineup):
        if type(lineup) == str:
            return lineup
        lineup = sorted(lineup)
        return '-'.join(lineup)

    def decode_lineup(self, lineup):
        if type(lineup) == list:
            return lineup
        return lineup.split('-')

    def parse_top_30(self):
        url = 'https://www.hltv.org/ranking/teams'
        r = self.session.get(url)
        if r.status_code != 200:
            if r.status_code == 429 or r.status_code == 403:
                try:
                    self.curr_proxy = next(self.proxies_iter)
                except StopIteration:
                    self.proxies_iter = self.make_proxies_iter()
                    self.curr_proxy = next(self.proxies_iter)
                r = self.session.get(url, proxies={'https': 'https://' + self.curr_proxy})
            else:
                raise Exception("can't parse top 30 status code is {}".format(r.status_code))
        soup = bs.BeautifulSoup(r.text, 'lxml')
        team_blocks = soup.find_all('div', attrs={'class': 'ranked-team standard-box'})
        lineups = set()
        for team_block in team_blocks:
            players = team_block.find_all('td', attrs={'class': 'player-holder'})
            lineup = []
            for player in players:
                lineup += [player.find('a')['href'].split('/')[2]]
            lineups.add(self.encode_lineup(lineup))
        return lineups

    def get_next_proxy(self):
        try:
            self.curr_proxy = next(self.proxies_iter)
        except StopIteration:
            self.proxies_iter = self.make_proxies_iter()
            self.curr_proxy = next(self.proxies_iter)
        print('changed proxy to {}'.format(self.curr_proxy))

    def get_page(self, url, params):
        self.counter += 1
        if self.counter == 100:
            self.counter = 0
            self.save_state()
            print('zzzz')
            time.sleep(200)
        if self.curr_proxy is None:
            r = self.session.get(url, params=params)
            if r.status_code != 200:
                if r.status_code == 429 or r.status_code == 403:
                    print("status code is {}".format(r.status_code))
                    self.get_next_proxy()
                    r = self.get_page(url, params)
                elif r.status_code == 500:
                    print('500 zzzz')
                    time.sleep(200)
                else:
                    raise Exception("status code is {}".format(r.status_code))
            return r

        try:
            r = self.session.get(url, params=params, proxies={'https': 'https://' + self.curr_proxy})
        except requests.exceptions.ConnectionError:
            print('connection error')
            self.get_next_proxy()
            r = self.get_page(url, params)
        if r.status_code != 200:
            if r.status_code == 429 or r.status_code == 403 or r.status_code == 500:
                print("status code is {}".format(r.status_code))
                self.get_next_proxy()
                r = self.get_page(url, params)
            else:
                raise Exception("status code is {}".format(r.status_code))
        return r

    def parse_match_by_id(self, match_id):
        print(match_id)
        if match_id in self.matches.keys():
            return self.matches[match_id]
        url = 'https://www.hltv.org/stats/matches/mapstatsid/' + str(match_id) + '/placeholder'
        r = self.get_page(url, None)
        soup = bs.BeautifulSoup(r.text, 'lxml')
        t1 = soup.find('div', attrs={'class': 'team-left'})
        t1_score = int(t1.find('div', attrs={'class': ['bold won', 'bold lost', 'bold']}).text)
        t2 = soup.find('div', attrs={'class': 'team-right'})
        t2_score = int(t2.find('div', attrs={'class': ['bold won', 'bold lost', 'bold']}).text)
        player_blocks = soup.find_all('td', attrs={'class': 'st-player'})
        players = []
        for player_block in player_blocks:
            players += [player_block.find('a')['href'].split('/')[3]]
        t1_players = players[:5]
        t2_players = players[5:]
        t1_players = self.encode_lineup(t1_players)
        t2_players = self.encode_lineup(t2_players)
        date = soup.find('div', attrs={'class': 'wide-grid'})\
            .find('span', attrs={'data-time-format': 'yyyy-MM-dd HH:mm'}).text
        match_info_box = soup.find('div', attrs={'class': 'match-info-box'})
        cs_map = match_info_box.text.split('\n')[2]
        tourney = match_info_box.find('a')['href'].split('=')[1]
        return {'t1_lineup': t1_players, 't2_lineup': t2_players,
                't1_score': t1_score, 't2_score': t2_score, 'date': date, 'map': cs_map, 'tourney': tourney}

    def find_lineups(self, match_ids):
        lineups = set()
        for match_id in match_ids:
            match = self.parse_match_by_id(match_id)
            self.matches[match_id] = match
            lineups.add(match['t1_lineup'])
            lineups.add(match['t2_lineup'])
        return lineups

    def parse_matches(self, lineups):
        match_ids = set()
        for lineup in lineups:
            match_ids |= self.parse_lineup_matches(lineup)
        return match_ids

    def parse_lineup_matches(self, lineup):
        print(lineup)
        url = 'https://www.hltv.org/stats/lineup/matches'
        lineup = self.decode_lineup(lineup)
        params = {
            'lineup': lineup,
            'minLineupMatch': self.min_lineup_match,
            }
        if self.start_date is not None:
            params['startDate'] = self.start_date
        if self.end_date is not None:
            params['endDate'] = self.end_date
        r = self.get_page(url, params)
        soup = bs.BeautifulSoup(r.text, 'lxml')
        match_blocks = soup.find_all('tr', attrs={'class': ['group-1 first', 'group-1 ', 'group-2 first', 'group-2 ']})
        match_ids = set()
        for match_block in match_blocks:
            match_id = match_block.find('a')['href'].split('/')[4]
            match_ids.add(match_id)
        return match_ids

    def parse_lineups_info(self, lineups):
        for lineup in lineups:
            print('parsing lineup info for ', lineup)
            self.lineups_info[lineup] = {}
            self.lineups_info[lineup]['Dust2'] = self.parse_map_info(lineup, 31)
            self.lineups_info[lineup]['Inferno'] = self.parse_map_info(lineup, 33)
            self.lineups_info[lineup]['Mirage'] = self.parse_map_info(lineup, 32)
            self.lineups_info[lineup]['Nuke'] = self.parse_map_info(lineup, 34)
            self.lineups_info[lineup]['Overpass'] = self.parse_map_info(lineup, 40)
            self.lineups_info[lineup]['Train'] = self.parse_map_info(lineup, 35)
            self.lineups_info[lineup]['Vertigo'] = self.parse_map_info(lineup, 46)

    def parse_map_info(self, lineup, map_code):
        info = {}
        url = 'https://www.hltv.org/stats/lineup/map/' + str(map_code)
        lineup = self.decode_lineup(lineup)
        params = {
            'lineup': lineup,
            'minLineupMatch': self.min_lineup_match,
        }
        if self.start_date is not None:
            params['startDate'] = self.start_date
        if self.end_date is not None:
            params['endDate'] = self.end_date
        r = self.get_page(url, params)
        soup = bs.BeautifulSoup(r.text, 'lxml')
        tp = soup.find('div', attrs={'class': 'stats-row'})
        info['times_played'] = tp.find_all('span')[1].text
        wdl = tp.find_next('div', attrs={'class': 'stats-row'})
        info['wins'], info['draws'], info['losses'] = wdl.find_all('span')[1].text.split('/')
        tot_rounds = wdl.find_next('div', attrs={'class': 'stats-row'})
        info['total_rounds_played'] = tot_rounds.find_all('span')[1].text
        rounds_won = tot_rounds.find_next('div', attrs={'class': 'stats-row'})
        info['rounds_won'] = rounds_won.find_all('span')[1].text
        wp = rounds_won.find_next('div', attrs={'class': 'stats-row'})
        info['win_percent'] = wp.find_all('span')[1].text
        pr_wp = wp.find_next('div', attrs={'class': 'stats-row'}).find_next('div', attrs={'class': 'stats-row'}). \
            find_next('div', attrs={'class': 'stats-row'})
        info['pistol_round_win_percent'] = pr_wp.find_all('span')[1].text[:-1]
        return info

    def make_graph(self):
        if self.from_state is not None:
            print('loading state from {}'.format(self.from_state))
            self.load_state(self.from_state)
        else:
            print('parsing top 30')
            self.new_lineups = self.parse_top_30()
            print('new lineups', self.new_lineups)
            self.old_matches = set()
        while True:
            print('parsing matches')
            self.new_matches = self.parse_matches(self.new_lineups) - self.old_matches
            print('new matches', self.new_matches)
            # print('parsing lineups info')
            # self.parse_lineups_info(self.new_lineups)
            self.lineups |= self.new_lineups
            print('parsing lineups')
            self.new_lineups = self.find_lineups(self.new_matches) - self.lineups
            self.old_matches |= self.new_matches
            print('new lineups', self.new_lineups)
            if len(self.new_matches) == 0:
                print('*****')
                break

    def matches_to_csv(self, file_name='matches.csv'):
        with open(file_name, 'w') as f:
            writer = csv.writer(f)
            writer.writerow(('id', 't1_lineup', 't2_lineup', 't1_score', 't2_score', 'date', 'map', 'tourney'))
            for match_id in self.matches:
                writer.writerow((match_id, self.matches[match_id]['t1_lineup'],
                                 self.matches[match_id]['t2_lineup'], self.matches[match_id]['t1_score'],
                                 self.matches[match_id]['t2_score'], self.matches[match_id]['date'],
                                 self.matches[match_id]['map'], self.matches[match_id]['tourney']))

    def lineups_to_csv(self, file_name='lineups.csv'):
        with open(file_name, 'w') as f:
            writer = csv.writer(f)
            header = ('lineup',)
            cs_maps = ('Dust2', 'Inferno', 'Mirage', 'Nuke', 'Overpass', 'Train', 'Vertigo')
            stats = ('times_played', 'wins', 'total_rounds_played', 'rounds_won', 'win_percent',
                     'pistol_round_win_percent')
            for cs_map, stat in itertools.product(cs_maps, stats):
                header += (cs_map + '_' + stat,)
            writer.writerow(header)
            for lineup in self.lineups_info:
                row = (lineup,)
                for cs_map, stat in itertools.product(cs_maps, stats):
                    row += (self.lineups_info[lineup][cs_map][stat],)
                writer.writerow(row)


def main():
    parser = MakeMatchesGraph(start_date='2013-01-01', min_lineup_match=5, from_state='f.txt')
    try:
        parser.make_graph()
    except Exception as e:
        print('exception in main: {}'.format(e))
        parser.save_state()
    parser.matches_to_csv()
    # parser.lineups_to_csv()
    parser.save_state()


if __name__ == '__main__':
    main()
