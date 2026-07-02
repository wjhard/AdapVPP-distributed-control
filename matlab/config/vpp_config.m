function cfg = vpp_config()
% VPP system global configuration.

%% Node parameters: six-node virtual power plant.
cfg.N = 6;
cfg.node_type = {'solar','solar','wind','wind','bess','load'};
cfg.node_name = {'PV1','PV2','Wind3','Wind4','BESS5','Load6'};

% Installed capacity [MW].
cfg.P_max = [50; 40; 60; 55; 30; 0];
cfg.P_min = [0;  0;  0;  0; -30; 0];

% Quadratic cost: C_i = a_i * P_i^2 + b_i * P_i.
cfg.cost_a = [0.018; 0.023; 0.014; 0.017; 0.050; 0];
cfg.cost_b = [1.450; 1.550; 1.150; 1.250; 2.000; 0];

%% Communication topology for the five controllable nodes.
% adj(i,j) = 1 means node i can receive information from node j.
cfg.adj = [0 1 0 1 0;
           1 0 1 0 0;
           0 1 0 1 1;
           1 0 1 0 1;
           0 0 1 1 0];

%% ADMM and distributed-iteration hyperparameters.
cfg.rho      = 0.1;
cfg.max_iter = 500;
cfg.tol      = 1e-4;
cfg.relax_standard = 0.25;
cfg.relax_robust   = 0.09;
cfg.consensus_gain = 0.02;

%% Event-trigger threshold.
cfg.delta = 0.05;

%% Communication scenarios.
cfg.scenario1.delay = 0;
cfg.scenario1.loss  = 0.00;
cfg.scenario1.name  = 'Ideal communication';

cfg.scenario2.delay = 2;
cfg.scenario2.loss  = 0.20;
cfg.scenario2.name  = 'Light weak communication';

cfg.scenario3.delay = 5;
cfg.scenario3.loss  = 0.50;
cfg.scenario3.name  = 'Heavy weak communication';

cfg.scenario4.delay = 2;
cfg.scenario4.loss  = 0.20;
cfg.scenario4.break_start = 100;
cfg.scenario4.break_end   = 200;
cfg.scenario4.name  = 'Communication outage recovery';

%% BESS parameters.
cfg.bess_soc_init = 0.50;
cfg.bess_soc_min  = 0.10;
cfg.bess_soc_max  = 0.90;
cfg.bess_efficiency = 0.95;

%% Reproducibility.
cfg.random_seed = 20260701;

end
