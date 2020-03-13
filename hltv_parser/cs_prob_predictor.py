import pandas as pd
import numpy as np
import pystan
import pickle
import datetime


class CSProbPredictor:

    def __init__(self):
        self.sm = None
        self.fit = None

    def train_predict(self, matches, tourney_matches):
        model_code = '''
        data
        {
            int<lower=0> n_teams;
            int<lower=0> n_matches;
            int<lower=0> n_tourney;
            int<lower=0, upper=n_teams> t1[n_matches + n_tourney];
            int<lower=0, upper=n_teams> t2[n_matches + n_tourney];
            int<lower=0, upper=1> y[n_matches]; // 1 if t1 wins 0 otherwise
        }

        parameters
        {
            real lambda[n_teams];
            real<lower=0> sigma;
        }

        transformed parameters
        {
            real<lower=0, upper=1> pi[n_tourney];
            for(i in 1:n_tourney)
            {
                pi[i] = inv_logit(lambda[t1[n_matches + i]] - lambda[t2[n_matches + i]]);
            }
        }

        model
        {
            vector[n_matches] theta;
            lambda ~ normal(0, sigma);
            for(i in 1:n_matches)
            {
                theta[i] = lambda[t1[i]] - lambda[t2[i]];
            }
            y ~ bernoulli_logit(theta);
        }
        '''
        lineups = set(matches['t1_lineup'].unique()).union(matches['t2_lineup'].unique()).\
            union(tourney_matches['t1_lineup'].unique()).union(tourney_matches['t2_lineup'].unique())
        lineup_f2id = dict(enumerate(lineups, 1))  # start from 1 for stan's one-based indexing
        lineup_id2f = {v: k for k, v in lineup_f2id.items()}

        matches = matches.sort_values(by=['date'], ascending=False)

        is_in_last_2_months = matches['date'] >= \
                              str(datetime.datetime.strptime(matches['date'].max(), '%Y-%m-%d %H:%M') -
                                  datetime.timedelta(days=61))
        stan_data = {
            'n_teams': len(lineups),
            'n_matches': len(matches),
            'n_tourney': len(tourney_matches),
            't1': matches['t1_lineup'].map(lineup_id2f).\
                append(tourney_matches['t1_lineup'].map(lineup_id2f)).to_numpy(),
            't2': matches['t2_lineup'].map(lineup_id2f).\
                append(tourney_matches['t2_lineup'].map(lineup_id2f)).to_numpy(),
            'y': matches.apply(lambda x: 1 if x['t1_score'] > x['t2_score'] else 0, axis=1)
        }
        self.sm = pystan.StanModel(model_code=model_code)
        self.fit = self.sm.sampling(data=stan_data, iter=1000, chains=4)
        with open("bradley-terry.pkl", "wb") as f:
            pickle.dump({'model_code': model_code, 'sm': self.sm, 'fit': self.fit}, f, protocol=-1)

        samples = self.fit.extract(permuted=True)
        pi = samples['pi']
        return pi
