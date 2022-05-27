import pytest
import itertools as it
import jax.numpy as jnp
import jax.random as jr
from jax.scipy.special import logsumexp

import ssm_jax.hmm.inference as core


def big_log_joint(initial_probs,
                  transition_matrix,
                  log_likelihoods):
    """Compute the big log joint probability array

    Args:
        initial_probs (_type_): _description_
        transition_matrix (_type_): _description_
        log_lkhds (_type_): _description_
    """
    num_timesteps, num_states = log_likelihoods.shape
    flat_log_joint = jnp.zeros(num_states**num_timesteps)

    # Compute each entry in the exponentially large log joint table
    for states in it.product(*([jnp.arange(num_states)] * num_timesteps)):
        states = jnp.array(states)
        lp = jnp.log(initial_probs[states[0]])
        lp += jnp.log(transition_matrix)[states[:-1], states[1:]].sum()
        lp += log_likelihoods[jnp.arange(num_timesteps), states].sum()
        flat_index = jnp.ravel_multi_index(states, (num_states,) * num_timesteps)
        flat_log_joint = flat_log_joint.at[flat_index].set(lp)

    return flat_log_joint.reshape((num_states,) * num_timesteps)


def random_hmm_args(key, num_timesteps, num_states):
    k1, k2, k3 = jr.split(key, 3)
    initial_probs = jr.uniform(k1, (num_states,))
    initial_probs /= initial_probs.sum()
    transition_matrix = jr.uniform(k2, (num_states, num_states))
    transition_matrix /= transition_matrix.sum(1, keepdims=True)
    log_likelihoods = jr.normal(k3, (num_timesteps, num_states))
    return initial_probs, transition_matrix, log_likelihoods


def test_hmm_filter(key=0, num_timesteps=3, num_states=2):
    if isinstance(key, int):
        key = jr.PRNGKey(key)

    initial_probs, transition_matrix, log_lkhds = \
        random_hmm_args(key, num_timesteps, num_states)

    # Run the HMM filter
    log_normalizer, filtered_probs, predicted_probs = \
        core.hmm_filter(initial_probs, transition_matrix, log_lkhds)

    # Compare log_normalizer to manually computed entries
    log_joint = big_log_joint(initial_probs, transition_matrix, log_lkhds)
    assert jnp.allclose(log_normalizer, logsumexp(log_joint))

    # Compare filtered_probs to manually computed entries
    for t in range(num_timesteps):
        log_joint_t = big_log_joint(
            initial_probs, transition_matrix, log_lkhds[:(t+1)])
        log_joint_t -= logsumexp(log_joint_t)
        filtered_probs_t = jnp.exp(logsumexp(log_joint_t, axis=tuple(jnp.arange(t))))
        assert jnp.allclose(filtered_probs[t], filtered_probs_t)

    # Compare predicted_probs to manually computed entries
    for t in range(num_timesteps):
        log_joint_t = big_log_joint(
            initial_probs, transition_matrix,
            jnp.row_stack([log_lkhds[:t], jnp.zeros(num_states)]))

        log_joint_t -= logsumexp(log_joint_t)
        predicted_probs_t = jnp.exp(logsumexp(log_joint_t, axis=tuple(jnp.arange(t))))
        assert jnp.allclose(predicted_probs[t], predicted_probs_t)


def test_two_filter_smoother(key=0, num_timesteps=5, num_states=2):
    if isinstance(key, int):
        key = jr.PRNGKey(key)

    args = random_hmm_args(key, num_timesteps, num_states)

    # Run the HMM filter
    posterior = core.hmm_two_filter_smoother(*args)

    # Compare log_normalizer to manually computed entries
    log_joint = big_log_joint(*args)
    assert jnp.allclose(posterior.marginal_log_lkhd, logsumexp(log_joint))

    # Compare the smooth probabilities to the manually computed ones
    joint = jnp.exp(log_joint - logsumexp(log_joint))
    for t in range(num_timesteps):
        smoothed_probs_t = jnp.sum(joint, axis=tuple(jnp.arange(t)) \
                                              +tuple(jnp.arange(t+1, num_timesteps)))
        assert jnp.allclose(posterior.smoothed_probs[t], smoothed_probs_t)


def test_hmm_smoother(key=0, num_timesteps=5, num_states=2):
    if isinstance(key, int):
        key = jr.PRNGKey(key)

    args = random_hmm_args(key, num_timesteps, num_states)

    # Run the HMM smoother
    posterior = core.hmm_smoother(*args)

    # Compare log_normalizer to manually computed entries
    log_joint = big_log_joint(*args)
    assert jnp.allclose(posterior.marginal_log_lkhd, logsumexp(log_joint))

    # Compare the smooth probabilities to the manually computed ones
    joint = jnp.exp(log_joint - logsumexp(log_joint))
    for t in range(num_timesteps):
        smoothed_probs_t = jnp.sum(joint, axis=tuple(jnp.arange(t)) \
                                              +tuple(jnp.arange(t+1, num_timesteps)))
        assert jnp.allclose(posterior.smoothed_probs[t], smoothed_probs_t)


def test_compute_transition_probs(key=0, num_timesteps=5, num_states=2):
    if isinstance(key, int):
        key = jr.PRNGKey(key)

    args = random_hmm_args(key, num_timesteps, num_states)

    # Run the HMM smoother
    posterior = core.hmm_smoother(*args)
    transition_probs = core.compute_transition_probs(args[1], posterior, reduce_sum=False)

    # Compare log_normalizer to manually computed entries
    log_joint = big_log_joint(*args)
    joint = jnp.exp(log_joint - logsumexp(log_joint))

    # Compare the smooth transition probabilities to the manually computed ones
    for t in range(num_timesteps - 1):
        trans_probs_t = jnp.sum(joint, axis=tuple(jnp.arange(t)) \
                                            +tuple(jnp.arange(t+2, num_timesteps)))
        assert jnp.allclose(transition_probs[t], trans_probs_t)


def test_compute_transition_probs_reduce(key=0, num_timesteps=5, num_states=2):
    if isinstance(key, int):
        key = jr.PRNGKey(key)

    args = random_hmm_args(key, num_timesteps, num_states)

    # Run the HMM smoother
    posterior = core.hmm_smoother(*args)
    sum_trans_probs = core.compute_transition_probs(args[1], posterior, reduce_sum=True)

    # Compare log_normalizer to manually computed entries
    log_joint = big_log_joint(*args)
    joint = jnp.exp(log_joint - logsumexp(log_joint))

    # Compare the smooth transition probabilities to the manually computed ones
    sum_trans_probs_t = 0
    for t in range(num_timesteps - 1):
        sum_trans_probs_t += jnp.sum(joint, axis=tuple(jnp.arange(t)) \
                                                 +tuple(jnp.arange(t+2, num_timesteps)))

    assert jnp.allclose(sum_trans_probs, sum_trans_probs_t)


def test_hmm_posterior_mode(key=0, num_timesteps=5, num_states=2):
    if isinstance(key, int):
        key = jr.PRNGKey(key)

    args = random_hmm_args(key, num_timesteps, num_states)

    # Run the HMM smoother
    mode = core.hmm_posterior_mode(*args)

    # Compare log_normalizer to manually computed entries and find the mode
    log_joint = big_log_joint(*args)
    mode_t = jnp.stack(jnp.unravel_index(jnp.argmax(log_joint), log_joint.shape))

    # Compare the posterior modes
    assert jnp.all(mode == mode_t)