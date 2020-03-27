import numpy as np
import pymc3 as pm
import pandas as pd
from scipy import stats
from pymc3.distributions import Interpolated
import datetime

class BayesianPredictor:

    def __init__(self, time_span=90, tune=5000, fit_iters=10000, pred_iters=2000, c=2):
        self.time_span = time_span
        self.fit_iters = fit_iters
        self.tune = tune
        self.pred_iters = pred_iters
        self.trace = None
        self.c = c
        self.lineup_f2id = None
        self.lineup_id2f = None

    def from_posterior(self, param, samples):
        smin, smax = np.min(samples), np.max(samples)
        width = smax - smin
        x = np.linspace(smin, smax, 100)
        y = stats.gaussian_kde(samples.T)(x)

        # what was never sampled should have a small probability but not 0,
        # so we'll extend the domain and use linear approximation of density on it
        x = np.concatenate([[x[0] - 3 * width], x, [x[-1] + 3 * width]])
        y = np.concatenate([[0], y, [0]])
        return Interpolated(param, x, y)

    def fit(self, matches, target):
        lineups = set(matches['t1_lineup'].unique()).union(matches['t2_lineup'].unique())
        self.lineup_f2id = dict(enumerate(lineups, 0))  # start from 0 for zero-based indexing
        self.lineup_id2f = {v: k for k, v in self.lineup_f2id.items()}
        t1 = matches['t1_lineup'].map(self.lineup_id2f)
        t2 = matches['t2_lineup'].map(self.lineup_id2f)
        # threshold_date = str(datetime.datetime.strptime(matches['date'].max(), '%Y-%m-%d %H:%M') -\
        #                     datetime.timedelta(days=self.time_span))
        # t1_older = matches[matches['date'] <= threshold_date]['t1_lineup'].map(self.lineup_id2f)
        # t2_older = matches[matches['date'] <= threshold_date]['t2_lineup'].map(self.lineup_id2f)
        # t1_newer = matches[matches['date'] > threshold_date]['t1_lineup'].map(self.lineup_id2f)
        # t2_newer = matches[matches['date'] > threshold_date]['t2_lineup'].map(self.lineup_id2f)
        t_num = len(lineups)  # number of teams
        # obs_older = target[matches['date'] <= threshold_date]
        # obs_newer = target[matches['date'] > threshold_date]
        # modeling older observations
        with pm.Model() as model:
            sigma = pm.HalfFlat('sigma', shape=t_num)
            alpha = pm.Normal('alpha', mu=0, sigma=sigma, shape=t_num)
            theta = pm.Deterministic('theta', alpha[t1] - alpha[t2])
            y = pm.Bernoulli('y', logit_p=theta, observed=target)
            self.trace = pm.sample(self.fit_iters, tune=self.tune)

        '''# modeling newer observations
        with pm.Model() as model:
            alpha = self.from_posterior('alpha', self.trace['alpha'] * self.c)
            theta = pm.Deterministic('theta', alpha[t1_newer] - alpha[t2_newer])
            y = pm.Bernoulli('y', logit_p=theta, observed=obs_newer)
            self.trace = pm.sample(self.fit_iters)'''

    def predict1(self, matches):
        t1 = matches['t1_lineup'].map(self.lineup_id2f)
        t2 = matches['t2_lineup'].map(self.lineup_id2f)
        with pm.Model() as model:
            alpha = self.from_posterior('alpha', self.trace['alpha'])
            theta = pm.Deterministic('theta', alpha[t1] - alpha[t2])
            p = pm.Deterministic('p', pm.math.exp(theta)/(pm.math.exp(theta) + 1))
            trace = pm.sample(self.pred_iters)
        return trace['p'].mean(axis=0)

    def predict(self, matches):
        alpha = self.trace['alpha'].mean(axis=0)
        t1 = matches['t1_lineup'].map(self.lineup_id2f).to_numpy(dtype='int64')
        t2 = matches['t2_lineup'].map(self.lineup_id2f).to_numpy(dtype='int64')
        exp_theta = np.exp(alpha[t1] - alpha[t2])
        return exp_theta/(exp_theta + 1)
