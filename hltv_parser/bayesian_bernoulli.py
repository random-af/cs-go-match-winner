import numpy as np
import pymc3 as pm
import pandas as pd
from scipy import stats
from pymc3.distributions import Interpolated

class BayesianPredictor:


    def __init__(self, iters=2000):
        self.iters = iters
        self.trace = None
        self.lineup_f2id = None
        self.lineup_id2f = None

    def from_posterior(self, param, samples):
        smin, smax = np.min(samples), np.max(samples)
        width = smax - smin
        x = np.linspace(smin, smax, 100)
        y = stats.gaussian_kde(samples)(x)

        # what was never sampled should have a small probability but not 0,
        # so we'll extend the domain and use linear approximation of density on it
        x = np.concatenate([[x[0] - 3 * width], x, [x[-1] + 3 * width]])
        y = np.concatenate([[0], y, [0]])
        return Interpolated(param, x, y)

    def train(self, matches, target):
        lineups = set(matches['t1_lineup'].unique()).union(matches['t2_lineup'].unique())
        self.lineup_f2id = dict(enumerate(lineups, 0))  # start from 0 for zero-based indexing
        self.lineup_id2f = {v: k for k, v in self.lineup_f2id.items()}
        t1 = matches['t1_lineup'].map(self.lineup_id2f)
        t2 = matches['t2_lineup'].map(self.lineup_id2f)
        t_num = len(lineups)  # number of teams
        m_num = len(matches)  # number of matches
        print(t_num, m_num)
        # obs = matches.apply(lambda x: 1 if x['t1_score'] > x['t2_score'] else 0, axis=1)  # 1 if t1 wins 0 otherwise
        with pm.Model() as model:
            sigma = pm.HalfFlat('sigma', shape=t_num)
            alpha = pm.Normal('alpha', mu=0, sigma=sigma, shape=t_num)
            theta = alpha[t1] - alpha[t2]
            y = pm.Bernoulli('y', logit_p=theta, observed=target)
            self.trace = pm.sample(self.iters)

    def predict(self, matches):
        alpha = self.trace['alpha'].mean(axis=0)
        t1 = matches['t1_lineup'].map(self.lineup_id2f)
        t2 = matches['t2_lineup'].map(self.lineup_id2f)
        exp_theta = np.exp(alpha[t1] - alpha[t2])
        return exp_theta/(exp_theta + 1)
