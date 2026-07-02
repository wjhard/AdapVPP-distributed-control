function result = run_scenario3b_standard_weak(P_demand, cfg)
% Scenario 3b: standard ADMM under the same heavy weak communication.

rng(cfg.random_seed + 30);
[P, lambda, conv, iter, diverged] = admm_standard_weak( ...
    P_demand, cfg, cfg.scenario3.delay, cfg.scenario3.loss);

comm_count = iter * 5;
result = build_scenario_result('Standard ADMM + heavy weak communication', ...
    P, lambda, conv, iter, comm_count, 0, P_demand, cfg, diverged);
result.method = 'Standard ADMM';

end
