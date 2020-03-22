import pandas as pd
import numpy as np
import itertools
import datetime


def fit_transform_data(tr, time_span):
    winner = np.where(tr['t1_score'] >= tr['t2_score'], tr['t1_lineup'], tr['t2_lineup'])
    loser = np.where(tr['t1_score'] >= tr['t2_score'], tr['t2_lineup'], tr['t1_lineup'])
    tr.at[:, 'Winner'] = winner
    tr.at[:, 'Loser'] = loser

    # generating statistics as features
    cs_maps = ('Dust2', 'Inferno', 'Mirage', 'Nuke', 'Overpass', 'Train', 'Vertigo')
    stats = ('times_played', 'wins')
    for cs_map, stat in itertools.product(cs_maps, stats):
        tr['t1_' + cs_map + '_' + stat] = np.zeros(tr.shape[0])
        tr['t2_' + cs_map + '_' + stat] = np.zeros(tr.shape[0])

    lineups = set(tr['t1_lineup'].unique()).union(tr['t2_lineup'].unique())
    lineups_info = {}
    for lineup in lineups:
        lineups_info[lineup] = {}
        lineup_matches = tr[(tr['t1_lineup'] == lineup) | (tr['t2_lineup'] == lineup)]
        indexes = lineup_matches.index
        lineups_info[lineup]['indexes'] = indexes
        for cs_map, stat in itertools.product(cs_maps, stats):
            lineups_info[lineup][cs_map + stat] = [0, ]

        for idx in indexes:
            lineup_match = lineup_matches.loc[idx]
            for cs_map in cs_maps:
                if lineup_match['map'] == cs_map:
                    lineups_info[lineup][cs_map + 'times_played'] += \
                        [lineups_info[lineup][cs_map + 'times_played'][-1] + 1]
                    if lineup_match['Winner'] == lineup:
                        lineups_info[lineup][cs_map + 'wins'] += [lineups_info[lineup][cs_map + 'wins'][-1] + 1]
                    else:
                        lineups_info[lineup][cs_map + 'wins'] += [lineups_info[lineup][cs_map + 'wins'][-1]]
                else:
                    lineups_info[lineup][cs_map + 'times_played'] += [
                        lineups_info[lineup][cs_map + 'times_played'][-1]]
                    lineups_info[lineup][cs_map + 'wins'] += [lineups_info[lineup][cs_map + 'wins'][-1]]

        for i in range(len(indexes)):
            date = lineup_matches.loc[indexes[i]]['date']
            form = '%Y-%m-%d %H:%M'
            j_span = 0
            for j in range(i, -1, -1):
                diff = datetime.datetime.strptime(date, form) - \
                       datetime.datetime.strptime(lineup_matches.loc[indexes[j]]['date'], form)
                if diff.days > time_span:
                    j_span = j + 1
                    break
            for cs_map, stat in itertools.product(cs_maps, stats):
                if lineup == tr['t1_lineup'].loc[indexes[i]]:
                    tr.at[indexes[i], 't1_' + cs_map + '_' + stat] = lineups_info[lineup][cs_map + stat][i] - \
                                                                     lineups_info[lineup][cs_map + stat][j_span]
                else:
                    tr.at[indexes[i], 't2_' + cs_map + '_' + stat] = lineups_info[lineup][cs_map + stat][i] - \
                                                                     lineups_info[lineup][cs_map + stat][j_span]
    for cs_map in cs_maps:
        tr['t1_' + cs_map + '_played_percent'] = np.zeros(tr.shape[0])
        tr['t2_' + cs_map + '_played_percent'] = np.zeros(tr.shape[0])
        tr['t1_' + cs_map + '_win_percent'] = np.zeros(tr.shape[0])
        tr['t2_' + cs_map + '_win_percent'] = np.zeros(tr.shape[0])

    for idx in tr.index:
        s1 = 0
        s2 = 0
        for cs_map in cs_maps:
            s1 += tr.loc[idx]['t1_' + cs_map + '_times_played']
            s2 += tr.loc[idx]['t2_' + cs_map + '_times_played']
        for cs_map in cs_maps:
            t1_times_played = tr.loc[idx]['t1_' + cs_map + '_times_played']
            t2_times_played = tr.loc[idx]['t2_' + cs_map + '_times_played']
            t1_wins = tr.loc[idx]['t1_' + cs_map + '_wins']
            t2_wins = tr.loc[idx]['t2_' + cs_map + '_wins']
            tr.at[idx, 't1_' + cs_map + '_played_percent'] = t1_times_played / s1 if s1 != 0 else 0
            tr.at[idx, 't1_' + cs_map + '_win_percent'] = t1_wins / t1_times_played if t1_times_played != 0 else 0
            tr.at[idx, 't2_' + cs_map + '_played_percent'] = t2_times_played / s2 if s2 != 0 else 0
            tr.at[idx, 't2_' + cs_map + '_win_percent'] = t2_wins / t2_times_played if t2_times_played != 0 else 0

    # saving lineups stats to use when predicting
    lineups_map_info = {}
    for lineup in lineups:
        lineups_map_info[lineup] = {}
        indexes = lineups_info[lineup]['indexes']
        date = tr.loc[indexes[-1]]['date']
        form = '%Y-%m-%d %H:%M'
        j_span = 0
        lineup_matches = tr[(tr['t1_lineup'] == lineup) | (tr['t2_lineup'] == lineup)]
        for j in range(len(indexes) - 1, -1, -1):
            diff = datetime.datetime.strptime(date, form) - \
                   datetime.datetime.strptime(lineup_matches.loc[indexes[j]]['date'], form)
            if diff.days > time_span:
                j_span = j + 1
                break
        for cs_map, stat in itertools.product(cs_maps, stats):
            lineups_map_info[lineup][cs_map + stat] = lineups_info[lineup][cs_map + stat][-1] - \
                                                           lineups_info[lineup][cs_map + stat][j_span]
    return tr, lineups_map_info


def compute_elo_rankings(data):
    """
    Given the list on matches in chronological order, for each match, computes
    the elo ranking of the 2 players at the beginning of the match

    """
    players = list(pd.Series(list(data.Winner) + list(data.Loser)).value_counts().index)
    elo = pd.Series(np.ones(len(players)) * 1500, index=players)
    ranking_elo = [(1500, 1500)]
    for i in range(1, len(data)):
        w = data.iloc[i - 1, :].Winner
        l = data.iloc[i - 1, :].Loser
        elow = elo[w]
        elol = elo[l]
        pwin = 1 / (1 + 10 ** ((elol - elow) / 400))
        K_win = 32
        K_los = 32
        new_elow = elow + K_win * (1 - pwin)
        new_elol = elol - K_los * (1 - pwin)
        elo[w] = new_elow
        elo[l] = new_elol
        ranking_elo.append((elo[data.iloc[i, :]['t1_lineup']], elo[data.iloc[i, :]['t2_lineup']]))
    ranking_elo = pd.DataFrame(ranking_elo, columns=["t1_elo", "t2_elo"])
    return ranking_elo, elo


def process_data(data, time_span=90):
    tr = data.sort_values(by=['date'])
    winner = np.where(tr['t1_score'] >= tr['t2_score'], tr['t1_lineup'], tr['t2_lineup'])
    loser = np.where(tr['t1_score'] >= tr['t2_score'], tr['t2_lineup'], tr['t1_lineup'])
    tr['Winner'] = winner
    tr['Loser'] = loser
    ranking_elo, lineups_elo = compute_elo_rankings(tr)
    tr, lineups_map_info = fit_transform_data(data, time_span)
    y = tr.apply(lambda d: 1 if d['t1_score'] > d['t2_score'] else 0, axis=1)
    y = y.reset_index().drop(columns=['index'])
    cs_maps = ('Dust2', 'Inferno', 'Mirage', 'Nuke', 'Overpass', 'Train', 'Vertigo')
    stats = ('times_played', 'wins')
    to_drop = ['t1_' + cs_map + '_' + stat for cs_map, stat in itertools.product(cs_maps, stats)] + \
              ['t2_' + cs_map + '_' + stat for cs_map, stat in itertools.product(cs_maps, stats)] + \
              ['id', 't1_lineup', 't2_lineup', 't1_score', 't2_score', 'date', 'map', 'tourney',
               'Winner', 'Loser']
    x = tr.drop(columns=to_drop)
    x = x.reset_index().drop(columns=['index'])
    x['elo_diff'] = ranking_elo['t1_elo'] - ranking_elo['t2_elo']
    x['t1_elo'] = ranking_elo['t1_elo']
    x['t2_elo'] = ranking_elo['t2_elo']
    return x, y, lineups_map_info, lineups_elo
