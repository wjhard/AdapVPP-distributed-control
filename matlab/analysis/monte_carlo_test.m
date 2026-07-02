function mc_summary_table = monte_carlo_test(num_runs, P_demand, cfg)
% Monte Carlo validation for weak communication scenarios.
%
% For each weak-communication condition, this compares:
%   1) standard ADMM without robustness;
%   2) event-triggered robust ADMM.

if nargin < 1 || isempty(num_runs)
    num_runs = 30;
end

this_file = mfilename('fullpath');
if isempty(this_file)
    project_root = pwd;
else
    project_root = fileparts(fileparts(fileparts(this_file)));
end

cd(project_root);
addpath(genpath(fullfile(project_root, 'matlab')));

if nargin < 3 || isempty(cfg)
    cfg = vpp_config();
end

if nargin < 2 || isempty(P_demand)
    data = load(fullfile(project_root, 'data', 'processed', 'matlab', 'vpp_typical_day.mat'));
    P_demand = data.P_load(12);
end

conditions = struct( ...
    'name', {'Light weak communication', 'Heavy weak communication'}, ...
    'delay', {cfg.scenario2.delay, cfg.scenario3.delay}, ...
    'loss', {cfg.scenario2.loss, cfg.scenario3.loss});

condition_col = cell(4, 1);
method_col = cell(4, 1);
iter_mean = zeros(4, 1);
iter_std = zeros(4, 1);
comm_saving_mean = zeros(4, 1);
comm_saving_std = zeros(4, 1);
diverged_cases = zeros(4, 1);
success_rate = zeros(4, 1);

row = 0;
for c = 1:numel(conditions)
    std_iters = zeros(num_runs, 1);
    std_savings = zeros(num_runs, 1);
    std_diverged = false(num_runs, 1);
    et_iters = zeros(num_runs, 1);
    et_savings = zeros(num_runs, 1);
    et_diverged = false(num_runs, 1);

    for r = 1:num_runs
        seed = cfg.random_seed + 1000 * c + r;

        rng(seed);
        [~, ~, ~, iter_std_run, diverged_std_run] = admm_standard_weak( ...
            P_demand, cfg, conditions(c).delay, conditions(c).loss);
        std_iters(r) = iter_std_run;
        std_savings(r) = 0;
        std_diverged(r) = diverged_std_run;

        rng(seed);
        [~, ~, ~, ~, comm_count, iter_et_run] = et_admm_robust( ...
            P_demand, cfg, conditions(c).delay, conditions(c).loss, inf, inf);
        et_iters(r) = iter_et_run;
        et_savings(r) = communication_saving(comm_count, iter_et_run);
        et_diverged(r) = false;
    end

    row = row + 1;
    condition_col{row} = conditions(c).name;
    method_col{row} = 'Standard ADMM weak';
    iter_mean(row) = mean(std_iters);
    iter_std(row) = std(std_iters);
    comm_saving_mean(row) = mean(std_savings);
    comm_saving_std(row) = std(std_savings);
    diverged_cases(row) = sum(std_diverged);
    success_rate(row) = (1 - diverged_cases(row) / num_runs) * 100;

    row = row + 1;
    condition_col{row} = conditions(c).name;
    method_col{row} = 'ET-ADMM robust';
    iter_mean(row) = mean(et_iters);
    iter_std(row) = std(et_iters);
    comm_saving_mean(row) = mean(et_savings);
    comm_saving_std(row) = std(et_savings);
    diverged_cases(row) = sum(et_diverged);
    success_rate(row) = (1 - diverged_cases(row) / num_runs) * 100;
end

mc_summary_table = table(condition_col, method_col, iter_mean, iter_std, ...
    comm_saving_mean, comm_saving_std, diverged_cases, success_rate, ...
    'VariableNames', {'Condition','Method','IterationMean','IterationStd', ...
    'CommSavingMean','CommSavingStd','DivergedCases','ConvergenceSuccessRate'});

fprintf('\n=== Monte Carlo Summary (%d runs per condition) ===\n', num_runs);
disp(mc_summary_table);

for i = 1:height(mc_summary_table)
    fprintf('%s | %s: iter %.2f +/- %.2f, comm saving %.2f +/- %.2f %%, success %.2f%%, diverged %d/%d\n', ...
        mc_summary_table.Condition{i}, mc_summary_table.Method{i}, ...
        mc_summary_table.IterationMean(i), mc_summary_table.IterationStd(i), ...
        mc_summary_table.CommSavingMean(i), mc_summary_table.CommSavingStd(i), ...
        mc_summary_table.ConvergenceSuccessRate(i), ...
        mc_summary_table.DivergedCases(i), num_runs);
end

results_dir = fullfile(project_root, 'matlab', 'results');
if ~exist(results_dir, 'dir')
    mkdir(results_dir);
end
save(fullfile(results_dir, 'monte_carlo_summary.mat'), 'mc_summary_table');

end
