function [x, resnorm, residual, exitflag, output, lambda, jacobian] = lsqnonlin(fun, x0, lb, ub, options)
% LSQNONLIN  Shim replacing Optimization Toolbox lsqnonlin.
%
% Minimises sum(fun(x).^2) using Newton-Raphson with bounds projection.
% Supports the calling conventions MAGEC uses:
%   x = lsqnonlin(fun, x0)
%   x = lsqnonlin(fun, x0, lb, ub)
%   x = lsqnonlin(fun, x0, lb, ub, options)

    if nargin < 3, lb = []; end
    if nargin < 4, ub = []; end
    if nargin < 5, options = struct(); end

    % --- Default parameters ---
    tol_fun  = 1e-10;
    tol_x    = 1e-10;
    max_iter = 400;
    max_fev  = 10000;

    if isstruct(options)
        if isfield(options, 'TolFun'),      tol_fun  = options.TolFun;      end
        if isfield(options, 'TolX'),         tol_x    = options.TolX;        end
        if isfield(options, 'MaxIter'),       max_iter = options.MaxIter;     end
        if isfield(options, 'MaxFunEvals'),   max_fev  = options.MaxFunEvals; end
        if isfield(options, 'FunctionTolerance'), tol_fun = options.FunctionTolerance; end
        if isfield(options, 'StepTolerance'),     tol_x   = options.StepTolerance;     end
        if isfield(options, 'MaxIterations'),      max_iter = options.MaxIterations;    end
        if isfield(options, 'MaxFunctionEvaluations'), max_fev = options.MaxFunctionEvaluations; end
    elseif isobject(options)
        try tol_fun  = options.FunctionTolerance;         catch; end
        try tol_x    = options.StepTolerance;             catch; end
        try max_iter = options.MaxIterations;              catch; end
        try max_fev  = options.MaxFunctionEvaluations;    catch; end
        try tol_fun  = options.TolFun;      catch; end
        try tol_x    = options.TolX;         catch; end
        try max_iter = options.MaxIter;       catch; end
        try max_fev  = options.MaxFunEvals;   catch; end
    end

    x  = x0(:);
    n  = numel(x);
    fev = 0;

    % Clamp to bounds
    if ~isempty(lb), x = max(x, lb(:)); end
    if ~isempty(ub), x = min(x, ub(:)); end

    F = fun(x); fev = fev + 1;
    F = F(:);

    for k = 1:max_iter
        % Numerical Jacobian
        J = zeros(numel(F), n);
        eps_j = max(1e-8, 1e-8 * abs(x));
        for j = 1:n
            xp = x;
            xp(j) = xp(j) + eps_j(j);
            if ~isempty(ub), xp = min(xp, ub(:)); end
            Fp = fun(xp); fev = fev + 1;
            J(:,j) = (Fp(:) - F) / eps_j(j);
        end

        if fev > max_fev, break; end

        % Gauss-Newton step: J'*J * dx = -J'*F
        JtJ = J' * J;
        JtF = J' * F;

        rcond_JtJ = rcond(JtJ);
        if rcond_JtJ < 1e-15 || isnan(rcond_JtJ)
            % Levenberg-Marquardt damping
            lambda_damp = 1e-6 * max(diag(JtJ));
            dx = -(JtJ + lambda_damp * eye(n)) \ JtF;
        else
            dx = -JtJ \ JtF;
        end

        % Line search
        alpha = 1.0;
        norm_F = norm(F);
        for ls = 1:10
            x_new = x + alpha * dx;
            if ~isempty(lb), x_new = max(x_new, lb(:)); end
            if ~isempty(ub), x_new = min(x_new, ub(:)); end
            F_new = fun(x_new); fev = fev + 1;
            if norm(F_new(:)) < norm_F || alpha < 1e-4
                break;
            end
            alpha = alpha * 0.5;
        end

        x = x_new;
        F = F_new(:);

        if norm(F) < tol_fun, break; end
        if norm(alpha * dx) < tol_x, break; end
    end

    x = reshape(x, size(x0));
    residual = reshape(F, size(fun(x0)));
    resnorm = sum(F.^2);

    if norm(F) < tol_fun
        exitflag = 1;
    elseif k >= max_iter
        exitflag = 0;
    else
        exitflag = -2;
    end

    output = struct('iterations', k, 'funcCount', fev, ...
                    'algorithm', 'lsqnonlin-shim', ...
                    'message', sprintf('lsqnonlin shim: %d iters, resnorm=%.2e', k, resnorm));
    lambda = struct();
    if nargout >= 7
        jacobian = J;
    end
end
