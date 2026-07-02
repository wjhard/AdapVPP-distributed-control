function result = run_scenario2b_standard_weak(P_demand, cfg)
% Scenario 2b: standard ADMM under the same light weak communication.

rng(cfg.random_seed + 20);
[P, lambda, conv, iter, diverged] = admm_standard_weak( ...
    P_demand, cfg, cfg.scenario2.delay, cfg.scenario2.loss);

comm_count = iter * 5;
result = build_scenario_result('Standard ADMM + light weak communication', ...
    P, lambda, conv, iter, comm_count, 0, P_demand, cfg, diverged);
result.method = 'Standard ADMM';

end
