function optimality_table = optimality_verification(P_demand, cfg)
% Verify ET-ADMM optimality against an independent centralized lambda solver.
%
% The economic dispatch problem is a strictly convex bounded quadratic
% program. For the interior optimum used in this case, equal incremental
% costs across all controllable nodes directly verify the KKT stationarity
% condition. This script prints and exports the centralized optimum P_star,
% the distributed ET-ADMM result P_opt, their deviation, and incremental
% costs for every communication scenario.

this_file = mfilename('fullpath');
if isempty(this_file)
    project_root = pwd;
else
    project_root = fileparts(fileparts(fileparts(this_file)));
end

cd(project_root);
addpath(genpath(fullfile(project_root, 'matlab')));

if nargin < 2 || isempty(cfg)
    cfg = vpp_config();
end

if nargin < 1 || isempty(P_demand)
    data_path = fullfile(project_root, 'data', 'processed', 'matlab', 'vpp_typical_day.mat');
    data = load(data_path, 'P_load');
    P_demand = data.P_load(12);
end

scenarios = build_et_scenarios(cfg);
n = numel(scenarios);
N_ctrl = 5;

scenario_col = cell(n, 1);
delay_col = zeros(n, 1);
loss_col = zeros(n, 1);
target_demand_col = zeros(n, 1);
iterations_col = zeros(n, 1);
comm_count_col = zeros(n, 1);
max_p_deviation_col = zeros(n, 1);
max_incremental_cost_spread_col = zeros(n, 1);
lambda_mean_col = zeros(n, 1);

P_star_cols = zeros(n, N_ctrl);
P_opt_cols = zeros(n, N_ctrl);
incremental_cost_cols = zeros(n, N_ctrl);

fprintf('\n=== Centralized Lambda Solver vs Distributed ET-ADMM Optimality Verification ===\n');
fprintf('Demand used for verification: %.6f MW\n', P_demand);

for s = 1:n
    item = scenarios(s);
    rng(cfg.random_seed + 500 + s);

    [P_star, lambda_star, target_demand] = economic_dispatch_solution(P_demand, cfg);
    [P_opt, lambda_opt, ~, ~, comm_count, iter_count] = et_admm_robust( ...
        P_demand, cfg, item.delay, item.loss, item.break_start, item.break_end);

    P_star = P_star(:);
    P_opt = P_opt(:);
    lambda_star = lambda_star(:);
    lambda_opt = lambda_opt(:);

    max_p_deviation = max(abs(P_opt - P_star));
    incremental_cost_spread = max(lambda_star) - min(lambda_star);

    scenario_col{s} = item.name;
    delay_col(s) = item.delay;
    loss_col(s) = item.loss;
    target_demand_col(s) = target_demand;
    iterations_col(s) = iter_count;
    comm_count_col(s) = comm_count;
    max_p_deviation_col(s) = max_p_deviation;
    max_incremental_cost_spread_col(s) = incremental_cost_spread;
    lambda_mean_col(s) = mean(lambda_star);
    P_star_cols(s, :) = P_star.';
    P_opt_cols(s, :) = P_opt.';
    incremental_cost_cols(s, :) = lambda_star.';

    fprintf('\n--- %s ---\n', item.name);
    fprintf('Centralized P_star [MW]: %s\n', vector_string(P_star));
    fprintf('ET-ADMM P_opt [MW]:      %s\n', vector_string(P_opt));
    fprintf('Max |P_opt - P_star|: %.6e MW\n', max_p_deviation);
    fprintf('Incremental costs at optimum: %s\n', vector_string(lambda_star));
    fprintf('Incremental cost spread: %.6e\n', incremental_cost_spread);
    fprintf('ET-ADMM lambda output: %s\n', vector_string(lambda_opt));
end

optimality_table = table(scenario_col, delay_col, loss_col, target_demand_col, ...
    iterations_col, comm_count_col, max_p_deviation_col, ...
    max_incremental_cost_spread_col, lambda_mean_col, ...
    P_star_cols(:, 1), P_star_cols(:, 2), P_star_cols(:, 3), P_star_cols(:, 4), P_star_cols(:, 5), ...
    P_opt_cols(:, 1), P_opt_cols(:, 2), P_opt_cols(:, 3), P_opt_cols(:, 4), P_opt_cols(:, 5), ...
    incremental_cost_cols(:, 1), incremental_cost_cols(:, 2), incremental_cost_cols(:, 3), ...
    incremental_cost_cols(:, 4), incremental_cost_cols(:, 5), ...
    'VariableNames', {'Scenario','DelaySteps','LossRate','TargetDemandMW', ...
    'ETIterations','ETCommCount','MaxPDeviationMW','MaxIncrementalCostSpread', ...
    'LambdaMean','PStar1','PStar2','PStar3','PStar4','PStar5', ...
    'POpt1','POpt2','POpt3','POpt4','POpt5', ...
    'IncrementalCost1','IncrementalCost2','IncrementalCost3', ...
    'IncrementalCost4','IncrementalCost5'});

fprintf('\n=== Optimality Verification Summary Table ===\n');
disp(optimality_table);

results_dir = fullfile(project_root, 'matlab', 'results');
if ~exist(results_dir, 'dir')
    mkdir(results_dir);
end
csv_path = fullfile(results_dir, 'optimality_verification.csv');
writetable(optimality_table, csv_path);
fprintf('\nSaved optimality verification table to %s\n', csv_path);

end

function scenarios = build_et_scenarios(cfg)
    scenarios = struct( ...
        'name', {cfg.scenario1.name, cfg.scenario2.name, cfg.scenario3.name, cfg.scenario4.name}, ...
        'delay', {cfg.scenario1.delay, cfg.scenario2.delay, cfg.scenario3.delay, cfg.scenario4.delay}, ...
        'loss', {cfg.scenario1.loss, cfg.scenario2.loss, cfg.scenario3.loss, cfg.scenario4.loss}, ...
        'break_start', {inf, inf, inf, cfg.scenario4.break_start}, ...
        'break_end', {inf, inf, inf, cfg.scenario4.break_end});
end

function text = vector_string(values)
    text = sprintf('%.6f ', values(:));
    text = ['[', strtrim(text), ']'];
end
