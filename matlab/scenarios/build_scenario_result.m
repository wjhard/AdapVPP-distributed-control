function result = build_scenario_result(name, P, lambda, conv, iter, comm_count, comm_saving, P_demand, cfg, diverged)
% Pack a scenario output into a uniform result structure.

if nargin < 10
    diverged = false;
end

result.name = name;
result.method = '';
result.P = P;
result.lambda = lambda;
result.conv = conv;
result.iter = iter;
result.comm = comm_count;
result.comm_saving = comm_saving;
result.diverged = logical(diverged);
result.total_cost = sum(cfg.cost_a(1:5) .* P .^ 2 + cfg.cost_b(1:5) .* P);
result.power_balance_error = sum(P) - P_demand;

end
