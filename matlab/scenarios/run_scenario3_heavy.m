function result = run_scenario3_heavy(P_demand, cfg)
% Scenario 3: heavy weak communication with larger delay and packet loss.

rng(cfg.random_seed + 3);
[P, lambda, conv, trigger_log, comm_count, iter] = et_admm_robust( ...
    P_demand, cfg, cfg.scenario3.delay, cfg.scenario3.loss, inf, inf);

result = build_scenario_result(cfg.scenario3.name, P, lambda, conv, iter, comm_count, ...
    communication_saving(comm_count, iter), P_demand, cfg);
result.trigger_log = trigger_log;
result.method = 'ET-ADMM robust';

end
