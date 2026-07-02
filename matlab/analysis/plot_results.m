function plot_results(results, cfg, P_demand)
% Plot comparison figures for ideal, weak, robust, and outage scenarios.

if nargin < 1 || isempty(results)
    data = load(fullfile('matlab', 'results', 'simulation_results.mat'), 'results', 'cfg', 'P_demand');
    results = data.results;
    cfg = data.cfg;
    P_demand = data.P_demand;
end

fields = {'scenario1','scenario2','scenario2b','scenario3','scenario3b','scenario4'};
labels = {'S1 Ideal','S2 ET light','S2b Std light','S3 ET heavy','S3b Std heavy','S4 Recovery'};
valid = isfield(results, fields);
fields = fields(valid);
labels = labels(valid);
n = numel(fields);

P_mat = zeros(5, n);
lambda_mat = zeros(5, n);
comm_savings = zeros(1, n);
P_totals = zeros(1, n);
diverged = false(1, n);

for i = 1:n
    item = results.(fields{i});
    P_mat(:, i) = item.P;
    lambda_mat(:, i) = item.lambda;
    comm_savings(i) = item.comm_saving;
    P_totals(i) = sum(item.P);
    if isfield(item, 'diverged')
        diverged(i) = item.diverged;
    end
end

fig = figure('Visible', 'off', 'Position', [100 100 1500 920]);
styles = {'b-', 'g--', 'k-.', 'r-.', 'c:', 'm-'};

subplot(2,3,1);
hold on;
for i = 1:n
    conv = max(results.(fields{i}).conv, eps);
    semilogy(conv, styles{min(i, numel(styles))}, 'LineWidth', 1.8);
end
xlabel('Iteration'); ylabel('Residual / target error');
title('Convergence Under Communication Impairments');
legend(labels, 'Location', 'northeast');
grid on;

subplot(2,3,2);
node_names = {'PV1','PV2','Wind3','Wind4','BESS5'};
bar(1:5, P_mat, 'grouped');
set(gca, 'XTick', 1:5, 'XTickLabel', node_names);
ylabel('Power [MW]'); title('Dispatch Result by Node');
legend(labels, 'Location', 'best');
grid on;

subplot(2,3,3);
bar(1:5, lambda_mat, 'grouped');
set(gca, 'XTick', 1:5, 'XTickLabel', node_names);
ylabel('Incremental cost'); title('Incremental Cost by Node');
legend(labels, 'Location', 'best');
grid on;

subplot(2,3,4);
bar(1:n, comm_savings, 'FaceColor', [0.2 0.6 0.8]);
set(gca, 'XTick', 1:n, 'XTickLabel', labels);
set(gca, 'XTickLabelRotation', 25);
ylabel('Communication saving [%]');
title('Communication Saving');
ylim([0 100]); grid on;

subplot(2,3,5);
iterations = zeros(1, n);
for i = 1:n
    iterations(i) = results.(fields{i}).iter;
end
bar(1:n, iterations, 'FaceColor', [0.45 0.45 0.75]); hold on;
for i = 1:n
    if diverged(i)
        text(i, iterations(i), 'diverged', 'Rotation', 90, ...
            'HorizontalAlignment', 'left', 'VerticalAlignment', 'middle', ...
            'Color', [0.75 0 0], 'FontWeight', 'bold');
    end
end
set(gca, 'XTick', 1:n, 'XTickLabel', labels);
set(gca, 'XTickLabelRotation', 25);
ylabel('Iterations'); title('Convergence Iterations');
grid on;

subplot(2,3,6);
bar(P_totals, 'FaceColor', [0.8 0.4 0.2]); hold on;
yline(P_demand, 'r--', 'Demand', 'LineWidth', 2);
set(gca, 'XTick', 1:n, 'XTickLabel', labels);
set(gca, 'XTickLabelRotation', 25);
ylabel('Total power [MW]'); title('Power Balance');
grid on;

results_dir = fullfile('matlab', 'results');
if ~exist(results_dir, 'dir')
    mkdir(results_dir);
end
print(fig, fullfile(results_dir, 'comparison_results.png'), '-dpng', '-r150');
close(fig);

fprintf('Comparison figure saved to matlab/results/comparison_results.png\n');

end
