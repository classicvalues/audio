"""
MVDR with torchaudio
====================

**Author** `Zhaoheng Ni <zni@fb.com>`__

"""

######################################################################
# Overview
# --------
#
# This is a tutorial on how to apply MVDR beamforming with
# :py:func:`torchaudio.transforms.MVDR`.
#
# Steps
#
# - Ideal Ratio Mask (IRM) is generated by dividing the clean/noise
#   magnitude by the mixture magnitude.
# - We test all three solutions (``ref_channel``, ``stv_evd``, ``stv_power``)
#   of torchaudio's MVDR module.
# - We test the single-channel and multi-channel masks for MVDR beamforming.
#   The multi-channel mask is averaged along channel dimension when computing
#   the covariance matrices of speech and noise, respectively.


######################################################################
# Preparation
# -----------
#
# First, we import the necessary packages and retrieve the data.
#
# The multi-channel audio example is selected from
# `ConferencingSpeech <https://github.com/ConferencingSpeech/ConferencingSpeech2021>`__
# dataset.
#
# The original filename is
#
#    ``SSB07200001\#noise-sound-bible-0038\#7.86_6.16_3.00_3.14_4.84_134.5285_191.7899_0.4735\#15217\#25.16333303751458\#0.2101221178590021.wav``
#
# which was generated with;
#
# - ``SSB07200001.wav`` from `AISHELL-3 <https://www.openslr.org/93/>`__ (Apache License v.2.0)
# - ``noise-sound-bible-0038.wav`` from `MUSAN <http://www.openslr.org/17/>`__ (Attribution 4.0 International — CC BY 4.0)  # noqa: E501
#

import os

import IPython.display as ipd
import requests
import torch
import torchaudio

torch.random.manual_seed(0)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

print(torch.__version__)
print(torchaudio.__version__)
print(device)

filenames = [
    "mix.wav",
    "reverb_clean.wav",
    "clean.wav",
]
base_url = "https://download.pytorch.org/torchaudio/tutorial-assets/mvdr"

for filename in filenames:
    os.makedirs("_assets", exist_ok=True)
    if not os.path.exists(filename):
        with open(f"_assets/{filename}", "wb") as file:
            file.write(requests.get(f"{base_url}/{filename}").content)

######################################################################
# Generate the Ideal Ratio Mask (IRM)
# -----------------------------------
#

######################################################################
# Loading audio data
# ~~~~~~~~~~~~~~~~~~
#

mix, sr = torchaudio.load("_assets/mix.wav")
reverb_clean, sr2 = torchaudio.load("_assets/reverb_clean.wav")
clean, sr3 = torchaudio.load("_assets/clean.wav")
assert sr == sr2

noise = mix - reverb_clean

######################################################################
#
# .. note::
#    The MVDR Module requires ``torch.cdouble`` dtype for noisy STFT.
#    We need to convert the dtype of the waveforms to ``torch.double``
#

mix = mix.to(torch.double)
noise = noise.to(torch.double)
clean = clean.to(torch.double)
reverb_clean = reverb_clean.to(torch.double)

######################################################################
# Compute STFT
# ~~~~~~~~~~~~
#

stft = torchaudio.transforms.Spectrogram(
    n_fft=1024,
    hop_length=256,
    power=None,
)
istft = torchaudio.transforms.InverseSpectrogram(n_fft=1024, hop_length=256)

spec_mix = stft(mix)
spec_clean = stft(clean)
spec_reverb_clean = stft(reverb_clean)
spec_noise = stft(noise)

######################################################################
# Generate the Ideal Ratio Mask (IRM)
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#
# .. note::
#    We found using the mask directly peforms better than using the
#    square root of it. This is slightly different from the definition of IRM.
#


def get_irms(spec_clean, spec_noise):
    mag_clean = spec_clean.abs() ** 2
    mag_noise = spec_noise.abs() ** 2
    irm_speech = mag_clean / (mag_clean + mag_noise)
    irm_noise = mag_noise / (mag_clean + mag_noise)

    return irm_speech, irm_noise


######################################################################
# .. note::
#    We use reverberant clean speech as the target here,
#    you can also set it to dry clean speech.

irm_speech, irm_noise = get_irms(spec_reverb_clean, spec_noise)

######################################################################
# Apply MVDR
# ----------
#

######################################################################
# Apply MVDR beamforming by using multi-channel masks
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#

results_multi = {}
for solution in ["ref_channel", "stv_evd", "stv_power"]:
    mvdr = torchaudio.transforms.MVDR(ref_channel=0, solution=solution, multi_mask=True)
    stft_est = mvdr(spec_mix, irm_speech, irm_noise)
    est = istft(stft_est, length=mix.shape[-1])
    results_multi[solution] = est

######################################################################
# Apply MVDR beamforming by using single-channel masks
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#
# We use the 1st channel as an example.
# The channel selection may depend on the design of the microphone array

results_single = {}
for solution in ["ref_channel", "stv_evd", "stv_power"]:
    mvdr = torchaudio.transforms.MVDR(ref_channel=0, solution=solution, multi_mask=False)
    stft_est = mvdr(spec_mix, irm_speech[0], irm_noise[0])
    est = istft(stft_est, length=mix.shape[-1])
    results_single[solution] = est

######################################################################
# Compute Si-SDR scores
# ~~~~~~~~~~~~~~~~~~~~~
#


def si_sdr(estimate, reference, epsilon=1e-8):
    estimate = estimate - estimate.mean()
    reference = reference - reference.mean()
    reference_pow = reference.pow(2).mean(axis=1, keepdim=True)
    mix_pow = (estimate * reference).mean(axis=1, keepdim=True)
    scale = mix_pow / (reference_pow + epsilon)

    reference = scale * reference
    error = estimate - reference

    reference_pow = reference.pow(2)
    error_pow = error.pow(2)

    reference_pow = reference_pow.mean(axis=1)
    error_pow = error_pow.mean(axis=1)

    sisdr = 10 * torch.log10(reference_pow) - 10 * torch.log10(error_pow)
    return sisdr.item()


######################################################################
# Results
# -------
#

######################################################################
# Single-channel mask results
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~
#

for solution in results_single:
    print(solution + ": ", si_sdr(results_single[solution][None, ...], reverb_clean[0:1]))

######################################################################
# Multi-channel mask results
# ~~~~~~~~~~~~~~~~~~~~~~~~~~
#

for solution in results_multi:
    print(solution + ": ", si_sdr(results_multi[solution][None, ...], reverb_clean[0:1]))

######################################################################
# Original audio
# --------------
#

######################################################################
# Mixture speech
# ~~~~~~~~~~~~~~
#

ipd.Audio(mix[0], rate=16000)

######################################################################
# Noise
# ~~~~~
#

ipd.Audio(noise[0], rate=16000)

######################################################################
# Clean speech
# ~~~~~~~~~~~~
#

ipd.Audio(clean[0], rate=16000)

######################################################################
# Enhanced audio
# --------------
#

######################################################################
# Multi-channel mask, ref_channel solution
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#

ipd.Audio(results_multi["ref_channel"], rate=16000)

######################################################################
# Multi-channel mask, stv_evd solution
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#

ipd.Audio(results_multi["stv_evd"], rate=16000)

######################################################################
# Multi-channel mask, stv_power solution
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#

ipd.Audio(results_multi["stv_power"], rate=16000)

######################################################################
# Single-channel mask, ref_channel solution
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#

ipd.Audio(results_single["ref_channel"], rate=16000)

######################################################################
# Single-channel mask, stv_evd solution
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#

ipd.Audio(results_single["stv_evd"], rate=16000)

######################################################################
# Single-channel mask, stv_power solution
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#

ipd.Audio(results_single["stv_power"], rate=16000)