function result = run_scenario2_light(P_demand, cfg)
% Scenario 2: light weak communication with delay and packet loss.

rng(cfg.random_seed + 2);
[P, lambda, conv, trigger_log, comm_count, iter] = et_admm_robust( ...
    P_demand, cfg, cfg.scenario2.delay, cfg.scenario2.loss, inf, inf);

result = build_scenario_result(cfg.scenario2.name, P, lambda, conv, iter, comm_count, ...
    communication_saving(comm_count, iter), P_demand, cfg);
result.trigger_log = trigger_log;
result.method = 'ET-ADMM robust';

end
