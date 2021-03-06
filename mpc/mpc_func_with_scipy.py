import numpy as np
import matplotlib.pyplot as plt
import math
import copy

from scipy.optimize import minimize
from scipy.optimize import LinearConstraint

class MpcController():
    """
    Attributes
    ------------
    A : numpy.ndarray
        system matrix
    B : numpy.ndarray
        input matrix
    Q : numpy.ndarray
        evaluation function weight
    R : numpy.ndarray
        evaluation function weight
    pre_step : int
        prediction step
    dt_input_upper : numpy.ndarray
        constraints of input dt
    dt_input_lower : numpy.ndarray
        constraints of input dt
    input_upper : numpy.ndarray
        constraints of input
    input_lower : numpy.ndarray
        constraints of input
    history_
    """
    def __init__(self, A, B, Q, R, pre_step, initial_input=None, dt_input_upper=None, dt_input_lower=None, input_upper=None, input_lower=None):
        """
        A : numpy.ndarray
            system matrix
        B : numpy.ndarray
            input matrix
        Q : numpy.ndarray
            evaluation function weight
        R : numpy.ndarray
            evaluation function weight
        pre_step : int
            prediction step
        dt_input_upper : numpy.ndarray
            constraints of input dt
        dt_input_lower : numpy.ndarray
            constraints of input dt
        input_upper : numpy.ndarray
            constraints of input
        input_lower : numpy.ndarray
            constraints of input
        """
        self.A = np.array(A)
        self.B = np.array(B)
        self.Q = np.array(Q)
        self.R = np.array(R)
        self.pre_step = pre_step

        self.Qs = None
        self.Rs = None

        self.state_size = self.A.shape[0]
        self.input_size = self.B.shape[1]

        self.history_us = [np.zeros(self.input_size)]

        # initial state
        if initial_input is not None:
            self.history_us = [initial_input]

        # constraints
        self.dt_input_lower = dt_input_lower
        self.dt_input_upper = dt_input_upper
        self.input_upper = input_upper
        self.input_lower = input_lower

        self.W = None
        self.omega = None
        self.F = None
        self.f = None
        
    def initialize_controller(self):
        """
        make matrix to calculate optimal control input
        """
        A_factorials = [self.A]

        self.phi_mat = copy.deepcopy(self.A)

        for _ in range(self.pre_step - 1):
            temp_mat = np.dot(A_factorials[-1], self.A)
            self.phi_mat = np.vstack((self.phi_mat, temp_mat))

            A_factorials.append(temp_mat) # after we use this factorials
            
        print("phi_mat = \n{0}".format(self.phi_mat))

        self.gamma_mat = copy.deepcopy(self.B)
        gammma_mat_temp = copy.deepcopy(self.B)
        
        for i in range(self.pre_step - 1):
            temp_1_mat = np.dot(A_factorials[i], self.B)
            gammma_mat_temp = temp_1_mat + gammma_mat_temp
            self.gamma_mat = np.vstack((self.gamma_mat, gammma_mat_temp))

        print("gamma_mat = \n{0}".format(self.gamma_mat))

        self.theta_mat = copy.deepcopy(self.gamma_mat)

        for i in range(self.pre_step - 1):
            temp_mat = np.zeros_like(self.gamma_mat)
            temp_mat[int((i + 1)*self.state_size): , :] = self.gamma_mat[:-int((i + 1)*self.state_size) , :]

            self.theta_mat = np.hstack((self.theta_mat, temp_mat))

        print("theta_mat = \n{0}".format(self.theta_mat))

        # evaluation function weight
        diag_Qs = np.array([np.diag(self.Q) for _ in range(self.pre_step)])
        diag_Rs = np.array([np.diag(self.R) for _ in range(self.pre_step)])
        
        self.Qs = np.diag(diag_Qs.flatten())
        self.Rs = np.diag(diag_Rs.flatten())

        print("Qs = \n{0}".format(self.Qs))
        print("Rs = \n{0}".format(self.Rs))

        # constraints
        # about dt U
        if self.input_lower is not None:
            # initialize
            self.F = np.zeros((self.input_size * 2, self.pre_step * self.input_size))
            for i in range(self.input_size):
                self.F[i * 2: (i + 1) * 2, i] = np.array([1.,  -1.])
                temp_F = copy.deepcopy(self.F)

            print("F = \n{0}".format(self.F))

            for i in range(self.pre_step - 1):
                temp_F = copy.deepcopy(temp_F)

                for j in range(self.input_size):
                    temp_F[j * 2: (j + 1) * 2, ((i+1) * self.input_size) + j] = np.array([1.,  -1.])
                
                self.F = np.vstack((self.F, temp_F))

            self.F1 = self.F[:, :self.input_size]
            
            temp_f = []

            for i in range(self.input_size):
                temp_f.append(-1 * self.input_upper[i])
                temp_f.append(self.input_lower[i])

            self.f = np.array([temp_f for _ in range(self.pre_step)]).flatten()

            print("F = \n{0}".format(self.F))
            print("F1 = \n{0}".format(self.F1))
            print("f = \n{0}".format(self.f))

        # about dt_u
        if self.dt_input_lower is not None:
            self.W = np.zeros((2, self.pre_step * self.input_size))
            self.W[:, 0] = np.array([1.,  -1.])

            for i in range(self.pre_step * self.input_size - 1):
                temp_W = np.zeros((2, self.pre_step * self.input_size))
                temp_W[:, i+1] = np.array([1.,  -1.])
                self.W = np.vstack((self.W, temp_W))

            temp_omega = []

            for i in range(self.input_size):
                temp_omega.append(self.dt_input_upper[i])
                temp_omega.append(-1. * self.dt_input_lower[i])

            self.omega = np.array([temp_omega for _ in range(self.pre_step)]).flatten()

            print("W = \n{0}".format(self.W))
            print("omega = \n{0}".format(self.omega))

        # about state
        print("check the matrix!! if you think rite, plese push enter")
        input()

    def calc_input(self, states, references):
        """calculate optimal input
        Parameters
        -----------
        states : numpy.array
            the size should have (state length * 1)
        references :
            the size should have (state length * pre_step)

        References
        ------------
        opt_input : numpy.ndarray
            optimal input, size is (1, input_length)
        """
        temp_1 = np.dot(self.phi_mat, states.reshape(-1, 1))
        temp_2 = np.dot(self.gamma_mat, self.history_us[-1].reshape(-1, 1))

        error = references.reshape(-1, 1) - temp_1 - temp_2

        G = 2. * np.dot(self.theta_mat.T, np.dot(self.Qs, error) )

        H = np.dot(self.theta_mat.T, np.dot(self.Qs, self.theta_mat)) + self.Rs

        # constraints
        A = [] 
        b = []

        if self.W is not None:
            A.append(self.W)
            b.append(self.omega.reshape(-1, 1))

        if self.F is not None:
            b_F = - np.dot(self.F1, self.history_us[-1].reshape(-1, 1)) - self.f.reshape(-1, 1)
            A.append(self.F)
            b.append(b_F)

        A = np.array(A).reshape(-1, self.input_size * self.pre_step)
        # b = np.array(b).reshape(-1, 1)
        ub = np.array(b).flatten()
        # print(np.dot(self.F1, self.history_us[-1].reshape(-1, 1)))

        def optimized_func(dt_us):
            """
            """
            temp_dt_us = np.array([dt_us[i] for i in range(self.input_size * self.pre_step)])

            return (np.dot(temp_dt_us, np.dot(H, temp_dt_us.reshape(-1, 1))) - np.dot(G.T, temp_dt_us.reshape(-1, 1)))[0]

        # constraint
        lb = np.array([-np.inf for _ in range(len(ub))])
        linear_cons = LinearConstraint(A, lb, ub)

        init_dt_us = np.zeros(self.input_size * self.pre_step)

        # constraint
        if self.W is not None or self.F is not None :
            # print("consider constraint!")
            opt_result = minimize(optimized_func, init_dt_us, constraints=[linear_cons])
        
        opt_dt_us = opt_result.x
        # print("current_u = {0}".format(self.history_us[-1]))
        # print("opt_dt_u = {0}".format(np.round(opt_dt_us, 5)))
        opt_u = opt_dt_us[:self.input_size] + self.history_us[-1]
        # print("opt_u = {0}".format(np.round(opt_u, 5)))
        # save
        self.history_us.append(opt_u)
        
        return opt_u




"""
constraint = []
for i in range(self.pre_step * self.input_size):
    sums = -1. * (np.dot(A[i], init_dt_us) - b[i])[0]
    constraint.append(sums)
"""