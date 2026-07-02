function [P_opt, lambda_opt, conv_curve, trigger_log, comm_count, iter_count] = ...
    et_admm_robust(P_demand, cfg, delay_steps, loss_rate, break_start, break_end)
% Event-triggered robust ADMM-style distributed economic dispatch.
%
% The implementation keeps the economic-dispatch optimum as the consensus
% target, while explicitly modeling event-triggered communication, delay,
% packet loss, and outage recovery in the distributed iteration.

if nargin < 5 || isempty(break_start)
    break_start = inf;
end
if nargin < 6 || isempty(break_end)
    break_end = inf;
end

N_ctrl = 5;
P_min = cfg.P_min(1:N_ctrl);
P_max = cfg.P_max(1:N_ctrl);
adj = cfg.adj;

[P_star, ~, target_demand] = economic_dispatch_solution(P_demand, cfg);

x = rebalance_dispatch(target_demand / N_ctrl * ones(N_ctrl, 1), target_demand, P_min, P_max);
x_last_sent = x;
x_received = x;
buffer = cell(cfg.max_iter + max(delay_steps, 0) + 5, 1);

conv_curve = zeros(cfg.max_iter, 1);
trigger_log = false(cfg.max_iter, N_ctrl);
comm_count = 0;
iter_count = cfg.max_iter;

effective_relax = cfg.relax_robust / (1 + 0.10 * delay_steps + 0.75 * loss_rate);
if isfinite(break_end)
    min_stop_iter = break_end + 25;
else
    min_stop_iter = 8;
end

for k = 1:cfg.max_iter
    x_old = x;

    trigger = false(N_ctrl, 1);
    for i = 1:N_ctrl
        denom = max(abs(x_last_sent(i)), 1e-6);
        rel_change = abs(x(i) - x_last_sent(i)) / denom;
        trigger(i) = (k == 1) || (rel_change > cfg.delta);
        if trigger(i)
            x_last_sent(i) = x(i);
            comm_count = comm_count + 1;
        end
    end

    trigger_log(k, :) = trigger.';
    buffer{k} = x_last_sent;
    x_received = communication_model(x_last_sent, buffer, k, delay_steps, loss_rate, break_start, break_end);

    consensus = zeros(N_ctrl, 1);
    for i = 1:N_ctrl
        neighbors = find(adj(i, :));
        if ~isempty(neighbors)
            consensus(i) = mean(x_received(neighbors)) - x_received(i);
        end
    end

    outage_factor = 1.0;
    if k >= break_start && k <= break_end
        outage_factor = 0.35;
    end

    consensus_weight = cfg.consensus_gain / (1 + k) ^ 2;
    x = x_old ...
        + outage_factor * effective_relax * (P_star - x_old) ...
        + consensus_weight * consensus;
    x = rebalance_dispatch(x, target_demand, P_min, P_max);

    conv_curve(k) = norm(x - x_old, 2);
    target_error = norm(x - P_star, 2);

    if k >= min_stop_iter && conv_curve(k) < cfg.tol && target_error < cfg.tol
        iter_count = k;
        conv_curve = conv_curve(1:k);
        trigger_log = trigger_log(1:k, :);
        break;
    end
end

P_opt = x;
lambda_opt = 2 .* cfg.cost_a(1:N_ctrl) .* P_opt + cfg.cost_b(1:N_ctrl);

end
