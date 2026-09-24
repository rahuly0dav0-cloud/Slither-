import numpy as np

def calculate_sas_matrix_rank(X, singularity_limit=1e-7):
    """
    Computes the rank of design matrix X mimicking SAS PROC REG / GLM logic.
    SAS evaluates the crossproduct matrix (X'X) diagonal pivots.
    """
    # 1. Add intercept column if not already present, to match SAS design matrices
    # X_design = np.column_stack([np.ones(X.shape[0]), X]) # Uncomment if X lacks intercept
    X_design = np.asarray(X, dtype=float)
    
    # 2. Compute the X'X crossproduct matrix
    XtX = np.dot(X_design.T, X_design)
    
    # 3. Cache original diagonals (equivalent to SAS baseline variance metrics)
    diagonals = np.diag(XtX)
    
    # 4. Perform Row-Echelon elimination checking against relative SAS tolerance
    n_features = XtX.shape[0]
    independent_columns = 0
    
    # Work on a copy to preserve original data
    A = XtX.copy()
    
    for i in range(n_features):
        # SAS checks if the pivot is less than (tolerance * original diagonal)
        # to catch near-singularities (collinearity)
        pivot_threshold = singularity_limit * diagonals[i]
        
        if A[i, i] > pivot_threshold:
            independent_columns += 1
            # Perform elimination step
            for j in range(i + 1, n_features):
                factor = A[j, i] / A[i, i]
                A[j, i:] -= factor * A[i, i:]
        else:
            # SAS marks this column as linearly dependent/zeroed out
            A[i, :] = 0 
            
    return independent_columns

# --- Verification Example ---
# Construct a matrix where column 3 is almost a perfect copy of column 2 (Collinear)
np.random.seed(42)
col1 = np.random.normal(0, 1, 100)
col2 = np.random.normal(0, 1, 100)
col3 = col2 + np.random.normal(0, 1e-6, 100) # Highly correlated

X = np.column_stack([np.ones(100), col1, col2, col3])

# Compare standard NumPy vs SAS Replication
numpy_rank = np.linalg.matrix_rank(X)
sas_rank = calculate_sas_matrix_rank(X, singularity_limit=1e-7)

print(f"NumPy Matrix Rank (SVD): {numpy_rank}")  # Might yield 4 (mathematically distinct)
print(f"SAS Replicated Matrix Rank: {sas_rank}") # Yields 3 (SAS drops column 3)