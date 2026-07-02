function [P_star, lambda_star, target_demand] = economic_dispatch_solution(P_demand, cfg)
% Solve the bounded quadratic economic dispatch problem for nodes 1-5.

N_ctrl = 5;
a = cfg.cost_a(1:N_ctrl);
b = cfg.cost_b(1:N_ctrl);
P_min = cfg.P_min(1:N_ctrl);
P_max = cfg.P_max(1:N_ctrl);

target_demand = min(max(P_demand, sum(P_min)), sum(P_max));

lambda_low = min(2 .* a .* P_min + b) - 100;
lambda_high = max(2 .* a .* P_max + b) + 100;

for iter = 1:120
    lambda_mid = 0.5 * (lambda_low + lambda_high);
    P_mid = min(max((lambda_mid - b) ./ (2 .* a), P_min), P_max);
    if sum(P_mid) < target_demand
        lambda_low = lambda_mid;
    else
        lambda_high = lambda_mid;
    end
end

lambda = 0.5 * (lambda_low + lambda_high);
P_star = min(max((lambda - b) ./ (2 .* a), P_min), P_max);
P_star = rebalance_dispatch(P_star, target_demand, P_min, P_max);
lambda_star = 2 .* a .* P_star + b;

end
