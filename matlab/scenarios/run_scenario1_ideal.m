function result = run_scenario1_ideal(P_demand, cfg)
% Scenario 1: ideal communication baseline.

[P, lambda, conv, iter] = admm_standard(P_demand, cfg);
result = build_scenario_result(cfg.scenario1.name, P, lambda, conv, iter, iter * 5, 0, P_demand, cfg);
result.method = 'Standard ADMM';

end
