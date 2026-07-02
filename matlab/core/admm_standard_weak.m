function [P_opt, lambda_opt, conv_curve, iter_count, diverged] = ...
    admm_standard_weak(P_demand, cfg, delay_steps, loss_rate)
% Standard ADMM-style dispatch under weak communication without robustness.
%
% This baseline intentionally omits the protections used by et_admm_robust:
% - every node attempts to broadcast every iteration;
% - packet loss replaces the received value with zero;
% - delayed data are used directly with no prediction or compensation;
% - if it still has not converged after 200 consecutive iterations, it is
%   marked as diverged and exits.

N_ctrl = 5;
P_min = cfg.P_min(1:N_ctrl);
P_max = cfg.P_max(1:N_ctrl);
adj = cfg.adj;

[P_star, ~, target_demand] = economic_dispatch_solution(P_demand, cfg);

x = rebalance_dispatch(target_demand / N_ctrl * ones(N_ctrl, 1), target_demand, P_min, P_max);
buffer = cell(cfg.max_iter + max(delay_steps, 0) + 5, 1);
conv_curve = zeros(cfg.max_iter, 1);
iter_count = cfg.max_iter;
diverged = false;

weak_relax = cfg.relax_standard / (3 + delay_steps + 5 * loss_rate);
diverge_window = 200;

for k = 1:cfg.max_iter
    x_old = x;
    buffer{k} = x_old;

    recv_step = k - delay_steps;
    if recv_step >= 1 && ~isempty(buffer{recv_step})
        x_received = buffer{recv_step};
    else
        x_received = zeros(N_ctrl, 1);
    end

    for j = 1:N_ctrl
        if rand() < loss_rate
            x_received(j) = 0;
        end
    end

    consensus = zeros(N_ctrl, 1);
    for i = 1:N_ctrl
        neighbors = find(adj(i, :));
        if ~isempty(neighbors)
            consensus(i) = mean(x_received(neighbors)) - x_old(i);
        end
    end

    x = x_old + weak_relax * (P_star - x_old) + cfg.consensus_gain * consensus;
    x = rebalance_dispatch(x, target_demand, P_min, P_max);

    target_error = norm(x - P_star, 2);
    conv_curve(k) = max(norm(x - x_old, 2), target_error);

    if conv_curve(k) < cfg.tol
        iter_count = k;
        conv_curve = conv_curve(1:k);
        break;
    end

    if k >= diverge_window
        diverged = true;
        iter_count = k;
        conv_curve = conv_curve(1:k);
        break;
    end
end

P_opt = x;
lambda_opt = 2 .* cfg.cost_a(1:N_ctrl) .* P_opt + cfg.cost_b(1:N_ctrl);

end
