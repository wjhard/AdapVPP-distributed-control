function cost_gap_table = cost_gap_analysis(results, cfg)
% Analyze economic loss caused by non-converged standard ADMM dispatch.
%
% Total_Cost = sum(cost_a_i * P_i^2 + cost_b_i * P_i), i = 1..5.
% The annualized loss uses the typical-dispatch hour extrapolated to 8760 h.

if nargin < 2
    data = load(fullfile('matlab', 'results', 'simulation_results.mat'), 'results', 'cfg');
    results = data.results;
    cfg = data.cfg;
end

hours_per_year = 24 * 365;

light = compute_gap_row('轻度弱通信', results.scenario2, results.scenario2b, cfg, hours_per_year);
heavy = compute_gap_row('重度弱通信', results.scenario3, results.scenario3b, cfg, hours_per_year);

condition = {light.condition; heavy.condition};
et_cost = [light.et_cost; heavy.et_cost];
standard_cost = [light.standard_cost; heavy.standard_cost];
cost_gap = [light.cost_gap; heavy.cost_gap];
annualized_loss = [light.annualized_loss; heavy.annualized_loss];
percent_gap = [light.percent_gap; heavy.percent_gap];

cost_gap_table = table(condition, et_cost, standard_cost, cost_gap, annualized_loss, percent_gap, ...
    'VariableNames', {'Condition','ETCost','StandardCost','HourlyCostGap','AnnualizedLoss','PercentGap'});

fprintf('\n=== Cost Gap Analysis: Standard ADMM vs ET-ADMM ===\n');
disp(cost_gap_table);

fprintf(['轻度弱通信下：标准ADMM因未收敛导致调度次优，年化经济损失约为%.2f元（按典型日外推），\n' ...
    '超出最优方案%.2f%%\n'], light.annualized_loss, light.percent_gap);
fprintf(['重度弱通信下：标准ADMM因未收敛导致调度次优，年化经济损失约为%.2f元（按典型日外推），\n' ...
    '超出最优方案%.2f%%\n'], heavy.annualized_loss, heavy.percent_gap);

results_dir = fullfile('matlab', 'results');
if ~exist(results_dir, 'dir')
    mkdir(results_dir);
end
save(fullfile(results_dir, 'cost_gap_analysis.mat'), 'cost_gap_table');
writetable(cost_gap_table, 'matlab/results/cost_gap_analysis.csv');

end

function row = compute_gap_row(condition, et_result, standard_result, cfg, hours_per_year)
    et_cost = dispatch_cost(et_result.P, cfg);
    standard_cost = dispatch_cost(standard_result.P, cfg);
    cost_gap = standard_cost - et_cost;

    row.condition = condition;
    row.et_cost = et_cost;
    row.standard_cost = standard_cost;
    row.cost_gap = cost_gap;
    row.annualized_loss = cost_gap * hours_per_year;
    row.percent_gap = cost_gap / max(abs(et_cost), eps) * 100;
end

function total_cost = dispatch_cost(P, cfg)
    P = P(:);
    a = cfg.cost_a(1:5);
    b = cfg.cost_b(1:5);
    total_cost = sum(a .* P .^ 2 + b .* P);
end
