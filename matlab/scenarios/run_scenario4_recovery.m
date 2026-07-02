function result = run_scenario4_recovery(P_demand, cfg)
% Scenario 4: weak communication with a temporary outage and recovery.

rng(cfg.random_seed + 4);
[P, lambda, conv, trigger_log, comm_count, iter] = et_admm_robust( ...
    P_demand, cfg, cfg.scenario4.delay, cfg.scenario4.loss, ...
    cfg.scenario4.break_start, cfg.scenario4.break_end);

result = build_scenario_result(cfg.scenario4.name, P, lambda, conv, iter, comm_count, ...
    communication_saving(comm_count, iter), P_demand, cfg);
result.trigger_log = trigger_log;
result.method = 'ET-ADMM robust';

end
