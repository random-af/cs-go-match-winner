import requests
import bs4 as bs
import csv
import asyncio
from proxybroker import Broker
from datetime import datetime


class MakeMatchesGraph:

    def __init__(self, start_date=None, end_date=None, min_lineup_match=5, from_state=None):
        self.session = requests.Session()
        self.session.headers = {
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_5) AppleWebKit/537.36 (KHTML, like Gecko) \
                            Chrome/79.0.3945.130 Safari/537.36'}
        self.lineups = set()
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
        return proxies_list

    def save_state(self):
        with open('f.txt', 'w') as f:
            f.write('lineups\n')
            for lineup in self.lineups:
                f.write(self.encode_lineup(lineup) + '\n')
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
                if line in ('lineups', 'matches', 'new_lineups', 'new_matches', 'old_matches', 'start date',
                            'end date', 'min lineup match'):
                    what_reading = line
                    continue
                if what_reading == 'lineups':
                    self.lineups.add(line)
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

    def parse_match_by_id(self, match_id):
        if match_id in self.matches.keys():
            return self.matches[match_id]
        url = 'https://www.hltv.org/stats/matches/mapstatsid/' + str(match_id) + '/placeholder'
        r = self.session.get(url, proxies={'https': 'https://' + self.curr_proxy})
        if r.status_code != 200:
            if r.status_code == 429 or r.status_code == 403:
                try:
                    self.curr_proxy = next(self.proxies_iter)
                except StopIteration:
                    self.proxies_iter = self.make_proxies_iter()
                    self.curr_proxy = next(self.proxies_iter)
                r = self.session.get(url, proxies={'https': 'https://' + self.curr_proxy})
            else:
                raise Exception("can't parse match {} status code is {}".format(match_id, r.status_code))
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
        return {'t1_lineup': t1_players, 't2_lineup': t2_players,
                't1_score': t1_score, 't2_score': t2_score, 'date': date}

    def parse_lineups(self, match_ids):
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
        r = self.session.get(url, params=params, proxies={'https': 'https://' + self.curr_proxy})
        if r.status_code != 200:
            if r.status_code == 429 or r.status_code == 403:
                try:
                    self.curr_proxy = next(self.proxies_iter)
                except StopIteration:
                    self.proxies_iter = self.make_proxies_iter()
                    self.curr_proxy = next(self.proxies_iter)
                r = self.session.get(url, params=params, proxies={'https': 'https://' + self.curr_proxy})
            else:
                raise Exception("can't parse lineup {} matches status code is {}".format(lineup, r.status_code))
        soup = bs.BeautifulSoup(r.text, 'lxml')
        match_blocks = soup.find_all('tr', attrs={'class': ['group-1 first', 'group-1 ', 'group-2 first', 'group-2 ']})
        match_ids = set()
        for match_block in match_blocks:
            match_id = match_block.find('a')['href'].split('/')[4]
            match_ids.add(match_id)
        return match_ids

    def make_graph(self):
        if self.from_state is not None:
            print('loading state from {}'.format(self.from_state))
            self.load_state(self.from_state)
        else:
            print('parsing top 30')
            self.new_lineups = self.parse_top_30()
            print(self.new_lineups)
            self.old_matches = set()
        while True:
            print('parsing matches')
            self.new_matches = self.parse_matches(self.new_lineups) - self.old_matches
            print(self.new_matches)
            self.lineups |= self.new_lineups
            print('parsing lineups')
            self.new_lineups = self.parse_lineups(self.new_matches) - self.lineups
            self.old_matches |= self.new_matches
            print(self.new_lineups)
            if len(self.new_matches) == 0:
                print('*****')
                break

    def matches_to_csv(self, file_name='matches.csv'):
        with open(file_name, 'w') as f:
            writer = csv.writer(f)
            writer.writerow(('id', 't1_lineup', 't2_lineup', 't1_score', 't2_score', 'date'))
            for match_id in self.matches:
                writer.writerow((match_id, self.matches[match_id]['t1_lineup'],
                                 self.matches[match_id]['t2_lineup'], self.matches[match_id]['t1_score'],
                                 self.matches[match_id]['t2_score'], self.matches[match_id]['date']))

    def lineups_to_csv(self, file_name='lineups.csv'):
        with open(file_name, 'w') as f:
            writer = csv.writer(f)
            writer.writerow(('lineup',))
            for lineup in self.lineups:
                writer.writerow((lineup,))


def main():
    parser = MakeMatchesGraph(start_date='2019-02-21', min_lineup_match=4, from_state='fff.txt')
    try:
        parser.make_graph()
    except Exception as e:
        print('exception in main: {}'.format(e))
        parser.save_state()
    parser.matches_to_csv()
    parser.lineups_to_csv()
    parser.save_state()


if __name__ == '__main__':
    main()
