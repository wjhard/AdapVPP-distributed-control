function P = rebalance_dispatch(P, P_demand, P_min, P_max)
% Rebalance dispatch inside box constraints so sum(P) matches P_demand.

P = min(max(P(:), P_min(:)), P_max(:));
target = min(max(P_demand, sum(P_min)), sum(P_max));

for iter = 1:80
    mismatch = target - sum(P);
    if abs(mismatch) < 1e-10
        break;
    end

    if mismatch > 0
        free = P < (P_max - 1e-10);
        room = P_max - P;
    else
        free = P > (P_min + 1e-10);
        room = P - P_min;
    end

    if ~any(free)
        break;
    end

    step = min(abs(mismatch) / nnz(free), max(room(free)));
    if step <= 0
        break;
    end

    if mismatch > 0
        P(free) = min(P_max(free), P(free) + step);
    else
        P(free) = max(P_min(free), P(free) - step);
    end
end

end
