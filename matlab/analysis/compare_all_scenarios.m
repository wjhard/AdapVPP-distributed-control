function [summary_table, weak_comparison_table] = compare_all_scenarios(results)
% Print final result tables for all scenarios and weak-communication pairs.

order = {'scenario1','scenario2','scenario2b','scenario3','scenario3b','scenario4'};
order = order(isfield(results, order));
n = numel(order);

scenario_names = cell(n, 1);
methods = cell(n, 1);
iterations = zeros(n, 1);
total_cost = zeros(n, 1);
comm_saving = zeros(n, 1);
balance_error = zeros(n, 1);
diverged = false(n, 1);

for i = 1:n
    item = results.(order{i});
    scenario_names{i} = item.name;
    methods{i} = item.method;
    iterations(i) = item.iter;
    total_cost(i) = item.total_cost;
    comm_saving(i) = item.comm_saving;
    balance_error(i) = item.power_balance_error;
    if isfield(item, 'diverged')
        diverged(i) = item.diverged;
    end
end

summary_table = table(scenario_names, methods, iterations, total_cost, ...
    comm_saving, balance_error, diverged, ...
    'VariableNames', {'Scenario','Method','Iterations','TotalCost', ...
    'CommSavingPercent','PowerBalanceErrorMW','Diverged'});

fprintf('\n=== Final Scenario Summary ===\n');
disp(summary_table);

weak_comparison_table = table();
if isfield(results, 'scenario2') && isfield(results, 'scenario2b') && ...
        isfield(results, 'scenario3') && isfield(results, 'scenario3b')
    condition = {'Light weak communication'; 'Heavy weak communication'};
    standard_iterations = [results.scenario2b.iter; results.scenario3b.iter];
    et_iterations = [results.scenario2.iter; results.scenario3.iter];
    standard_diverged = [results.scenario2b.diverged; results.scenario3b.diverged];
    et_diverged = [results.scenario2.diverged; results.scenario3.diverged];
    standard_comm_saving = [results.scenario2b.comm_saving; results.scenario3b.comm_saving];
    et_comm_saving = [results.scenario2.comm_saving; results.scenario3.comm_saving];
    standard_cost = [results.scenario2b.total_cost; results.scenario3b.total_cost];
    et_cost = [results.scenario2.total_cost; results.scenario3.total_cost];

    weak_comparison_table = table(condition, standard_iterations, et_iterations, ...
        standard_diverged, et_diverged, standard_comm_saving, et_comm_saving, ...
        standard_cost, et_cost, ...
        'VariableNames', {'Condition','StandardIterations','ETIterations', ...
        'StandardDiverged','ETDiverged','StandardCommSavingPercent', ...
        'ETCommSavingPercent','StandardCost','ETCost'});

    fprintf('\n=== Standard ADMM vs ET-ADMM Under Same Weak Communication ===\n');
    disp(weak_comparison_table);
end

end
