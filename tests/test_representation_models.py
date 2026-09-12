import torch

from poweshift_backend.representation.models import CandidateConfig, build_candidate


def test_gru_and_transformer_decode_bounded_profiles_with_a_previous_latent() -> None:
    features = torch.ones((1, 3, 2), dtype=torch.float32)
    valid = torch.tensor([[[True, True], [True, True], [False, False]]])
    previous_latent = torch.zeros((1, 4), dtype=torch.float32)
    config = CandidateConfig(feature_width=2, latent_width=4, hidden_width=8, layers=2, heads=2, feedforward_width=16)

    for kind in ("gru", "transformer"):
        output = build_candidate(kind, config)(features, valid, previous_latent)
        assert output.shape == (1, 4)
        assert torch.all((output >= 0.0) & (output <= 1.0))


def test_candidates_return_a_real_next_latent_through_the_shared_decoder() -> None:
    features = torch.ones((1, 3, 2), dtype=torch.float32)
    valid = torch.ones_like(features, dtype=torch.bool)
    previous = torch.zeros((1, 4), dtype=torch.float32)
    config = CandidateConfig(feature_width=2, latent_width=4, hidden_width=8, layers=2, heads=2, feedforward_width=16)

    for kind in ("gru", "transformer"):
        model = build_candidate(kind, config)
        profile, latent = model.update(features, valid, previous)

        assert latent.shape == (1, 4)
        assert profile.shape == (1, 4)
        assert torch.allclose(profile, model.decode(latent))
        assert torch.allclose(profile, model(features, valid, previous))


def test_candidates_expose_positive_component_variance_for_gaussian_nll() -> None:
    features = torch.ones((2, 3, 2), dtype=torch.float32)
    valid = torch.ones_like(features, dtype=torch.bool)
    previous = torch.zeros((2, 4), dtype=torch.float32)
    config = CandidateConfig(feature_width=2, latent_width=4, hidden_width=8, layers=2, heads=2, feedforward_width=16, variance_floor=0.01)

    for kind in ("gru", "transformer"):
        model = build_candidate(kind, config)
        mean, variance, latent = model.distribution(features, valid, previous)
        loss = torch.nn.functional.gaussian_nll_loss(mean, torch.full_like(mean, 0.5), variance, full=True)
        loss.backward()

        assert mean.shape == variance.shape == (2, 4)
        assert latent.shape == (2, 4)
        assert torch.all((mean >= 0.0) & (mean <= 1.0))
        assert torch.isfinite(variance).all()
        assert torch.all(variance >= 0.01)
        assert model.decoder.variance.weight.grad is not None


def test_gru_keeps_one_batch_member_independent_of_another() -> None:
    torch.manual_seed(7)
    model = build_candidate("gru", CandidateConfig(feature_width=2, latent_width=4, hidden_width=8, layers=2, heads=2, feedforward_width=16))
    first = torch.tensor([[[1.0, 2.0], [3.0, 4.0]]])
    first_valid = torch.ones_like(first, dtype=torch.bool)
    first_latent = torch.zeros((1, 4))
    paired = torch.cat((first, torch.full_like(first, 99.0)))
    paired_valid = torch.ones_like(paired, dtype=torch.bool)
    paired_latent = torch.zeros((2, 4))

    assert torch.allclose(model(first, first_valid, first_latent)[0], model(paired, paired_valid, paired_latent)[0])


def test_models_ignore_masked_nan_values_and_keep_interior_gaps_masked() -> None:
    features = torch.tensor([[[1.0, 2.0], [float("nan"), float("nan")], [3.0, 4.0]]])
    valid = torch.tensor([[[True, True], [False, False], [True, True]]])
    latent = torch.zeros((1, 4))
    config = CandidateConfig(feature_width=2, latent_width=4, hidden_width=8, layers=2, heads=2, feedforward_width=16)

    for kind in ("gru", "transformer"):
        assert torch.isfinite(build_candidate(kind, config)(features, valid, latent)).all()


def test_transformer_encodes_timestep_order() -> None:
    torch.manual_seed(9)
    model = build_candidate("transformer", CandidateConfig(feature_width=2, latent_width=4, hidden_width=8, layers=2, heads=2, feedforward_width=16))
    valid = torch.ones((1, 3, 2), dtype=torch.bool)
    latent = torch.zeros((1, 4))
    forward = torch.tensor([[[1.0, 0.0], [2.0, 0.0], [3.0, 0.0]]])
    reversed_values = forward.flip(1)

    assert not torch.allclose(model(forward, valid, latent), model(reversed_values, valid, latent))
