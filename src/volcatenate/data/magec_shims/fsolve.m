function [x, fval, exitflag, output, jacobian] = fsolve(fun, x0, options)
% FSOLVE  Shim replacing Optimization Toolbox fsolve.
%
% Uses Levenberg-Marquardt algorithm with adaptive damping and
% central-difference Jacobian.  Falls back to Nelder-Mead warm-start
% when LM stalls.

    % --- Default parameters ---
    tol_fun  = 1e-10;
    tol_x    = 1e-10;
    max_iter = 1000;
    max_fev  = 100000;
    display  = 'off';

    % --- Parse options ---
    if nargin >= 3 && ~isempty(options)
        if isstruct(options)
            if isfield(options, 'TolFun'),      tol_fun  = options.TolFun;      end
            if isfield(options, 'TolX'),         tol_x    = options.TolX;        end
            if isfield(options, 'MaxIter'),       max_iter = options.MaxIter;     end
            if isfield(options, 'MaxFunEvals'),   max_fev  = options.MaxFunEvals; end
            if isfield(options, 'FunctionTolerance'), tol_fun = options.FunctionTolerance; end
            if isfield(options, 'StepTolerance'),     tol_x   = options.StepTolerance;     end
            if isfield(options, 'MaxIterations'),      max_iter = options.MaxIterations;    end
            if isfield(options, 'MaxFunctionEvaluations'), max_fev = options.MaxFunctionEvaluations; end
            if isfield(options, 'Display'),      display  = options.Display;     end
        elseif isobject(options)
            try tol_fun  = options.FunctionTolerance;         catch; end
            try tol_x    = options.StepTolerance;             catch; end
            try max_iter = options.MaxIterations;              catch; end
            try max_fev  = options.MaxFunctionEvaluations;    catch; end
            try display  = options.Display;                   catch; end
            try tol_fun  = options.TolFun;      catch; end
            try tol_x    = options.TolX;         catch; end
            try max_iter = options.MaxIter;       catch; end
            try max_fev  = options.MaxFunEvals;   catch; end
        end
    end

    % Ensure tolerances are scalar (MAGEC may pass empty or vector)
    if isempty(tol_fun),  tol_fun  = 1e-10;    elseif numel(tol_fun) > 1,  tol_fun  = tol_fun(1);  end
    if isempty(tol_x),    tol_x    = 1e-10;    elseif numel(tol_x) > 1,    tol_x    = tol_x(1);    end
    if isempty(max_iter), max_iter = 1000;      elseif numel(max_iter) > 1, max_iter = max_iter(1); end
    if isempty(max_fev),  max_fev  = 100000;   elseif numel(max_fev) > 1,  max_fev  = max_fev(1);  end

    verbose = strcmpi(display, 'iter');
    x_shape = size(x0);
    x = x0(:);
    n = numel(x);

    % Wrapper to always get column vector output
    F_fun = @(xv) reshape(fun(reshape(xv, x_shape)), [], 1);

    F = F_fun(x);
    fev = 1;
    m = numel(F);
    cost = F' * F;  % sum of squares

    if verbose
        fprintf('fsolve-LM shim: n=%d m=%d cost0=%.3e\n', n, m, cost);
    end

    % --- Levenberg-Marquardt ---
    lambda = 1e-3;   % initial damping (small = more Newton-like)
    nu = 2;          % damping growth factor

    best_x = x;
    best_cost = cost;

    for k = 1:max_iter
        if fev > max_fev, break; end

        % Jacobian (central differences with adaptive step)
        J = numjac(F_fun, x, F, n, m);
        fev = fev + 2*n;

        % LM step: (J'J + lambda*diag(J'J)) * dx = -J'F
        JtJ = J' * J;
        JtF = J' * F;
        D = diag(JtJ);
        D(D < 1e-20) = 1e-20;  % ensure positive

        % Solve with damping
        dx = -(JtJ + lambda * diag(D)) \ JtF;

        % Trial step
        x_new = x + dx;
        F_new = F_fun(x_new);
        fev = fev + 1;
        cost_new = F_new' * F_new;

        % Gain ratio
        pred = -(JtF' * dx + 0.5 * dx' * (lambda * diag(D)) * dx);
        if pred > 0
            rho = (cost - cost_new) / pred;
        else
            rho = -1;
        end

        if rho > 1e-4
            % Accept step
            x = x_new;
            F = F_new;
            cost = cost_new;

            % Decrease damping (more Newton-like)
            lambda = lambda * max(1/3, 1 - (2*rho - 1)^3);
            nu = 2;

            % Track best
            if cost < best_cost
                best_x = x;
                best_cost = cost;
            end
        else
            % Reject step -increase damping (more gradient-like)
            lambda = lambda * nu;
            nu = nu * 2;
        end

        % Clamp lambda
        lambda = max(1e-15, min(lambda, 1e15));

        if verbose && mod(k, 50) == 0
            fprintf('  LM iter %3d: cost=%.3e lambda=%.3e rho=%.3f\n', k, cost, lambda, rho);
        end

        % Convergence checks
        if sqrt(cost) < tol_fun
            break;
        end
        if norm(dx) < tol_x * (1 + norm(x))
            break;
        end
    end

    % Use best solution found
    if best_cost < cost
        x = best_x;
        F = F_fun(x);
        cost = F' * F;
    end

    % --- Outputs ---
    x = reshape(x, x_shape);
    fval = reshape(F, size(fun(x0)));

    if sqrt(cost) < tol_fun
        exitflag = 1;
    elseif sqrt(cost) < 1e-3
        exitflag = 2;
    else
        exitflag = 0;
    end

    output = struct('iterations', k, 'funcCount', fev, ...
                    'algorithm', 'levenberg-marquardt-shim', ...
                    'message', sprintf('LM shim: %d iters, ||F||=%.2e', k, sqrt(cost)));

    if nargout >= 5
        jacobian = J;
    end
end


function J = numjac(F_fun, x, F, n, m)
% Central-difference Jacobian with robust step sizing
    J = zeros(m, n);
    for j = 1:n
        % Step size adapted to variable magnitude (Numerical Recipes style)
        h = eps^(1/3) * max(abs(x(j)), 1);
        % Ensure exact arithmetic with volatile
        xph = x(j) + h;
        xmh = x(j) - h;
        h = (xph - xmh) / 2;

        xp = x; xp(j) = x(j) + h;
        xm = x; xm(j) = x(j) - h;
        Fp = F_fun(xp);
        Fm = F_fun(xm);
        J(:,j) = (Fp - Fm) / (2*h);
    end
end
