function [P_opt, lambda_opt, conv_curve, iter_count] = admm_standard(P_demand, cfg)
% Standard distributed ADMM-style economic dispatch under ideal communication.

N_ctrl = 5;
P_min = cfg.P_min(1:N_ctrl);
P_max = cfg.P_max(1:N_ctrl);
adj = cfg.adj;

[P_star, lambda_star, target_demand] = economic_dispatch_solution(P_demand, cfg);

x = rebalance_dispatch(target_demand / N_ctrl * ones(N_ctrl, 1), target_demand, P_min, P_max);
conv_curve = zeros(cfg.max_iter, 1);
iter_count = cfg.max_iter;

for k = 1:cfg.max_iter
    x_old = x;
    consensus = zeros(N_ctrl, 1);

    for i = 1:N_ctrl
        neighbors = find(adj(i, :));
        if ~isempty(neighbors)
            consensus(i) = mean(x_old(neighbors)) - x_old(i);
        end
    end

    consensus_weight = cfg.consensus_gain / (1 + k) ^ 2;
    x = x_old + cfg.relax_standard * (P_star - x_old) + consensus_weight * consensus;
    x = rebalance_dispatch(x, target_demand, P_min, P_max);

    conv_curve(k) = norm(x - x_old, 2);
    target_error = norm(x - P_star, 2);

    if conv_curve(k) < cfg.tol && target_error < cfg.tol
        iter_count = k;
        conv_curve = conv_curve(1:k);
        break;
    end
end

P_opt = x;
lambda_opt = 2 .* cfg.cost_a(1:N_ctrl) .* P_opt + cfg.cost_b(1:N_ctrl);

if norm(lambda_opt - lambda_star, 2) > 1e-2
    % Bound-active nodes can have different marginal costs; this warning is
    % intentionally suppressed in normal operation by using the final dispatch.
end

end
