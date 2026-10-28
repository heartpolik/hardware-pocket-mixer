// SPDX-License-Identifier: GPL-3.0-or-later
#include "mixer.h"

#include <math.h>
#include <string.h>

#include "recorder.h"

using namespace dsp;

static constexpr float EQ_HI_HZ = 8000.f, EQ_MID_HZ = 1000.f, EQ_MID_Q = 0.7f, EQ_LO_HZ = 120.f;

void Mixer::init(float fs, Scene* scene, Live* live, int16_t* fxPool[NFX], uint32_t fxPoolSize) {
    fs_ = fs;
    s_ = scene;
    l_ = live;
    for (int c = 0; c < NCH; c++) {
        ch_[c] = Channel();
        ch_[c].comp.setup(fs);
        for (int k = 0; k < 2; k++) chMeter[c][k].setup(fs, MAX_BLOCK);
    }
    for (int k = 0; k < 2; k++) {
        mainMeter[k].setup(fs, MAX_BLOCK);
        auxMeter[k].setup(fs, MAX_BLOCK);
        phonesMeter[k].setup(fs, MAX_BLOCK);
    }
    for (int i = 0; i < NFX; i++) fx_[i].init(fs, fxPool[i], fxPoolSize);
    lim_.setup(fs);
}

bool Mixer::anyCue() const {
    for (int c = 0; c < NCH; c++)
        if (s_->ch[c].cue) return true;
    return false;
}

// Recompute filters only when their parameters change (encoders move a few values per block at most).
void Mixer::updateChannel(int c) {
    Channel& k = ch_[c];
    const ChannelParams& p = s_->ch[c];
    if (p.filter != k.cFilter) {
        k.cFilter = p.filter;
        float f = p.filter;
        if (fabsf(f) < 0.02f) k.flt = BiquadCoefs();
        else if (f < 0) k.flt.lowpass(fs_, 20000.f * powf(100.f / 20000.f, -f), 0.8f);    // 20 kHz -> 100 Hz
        else k.flt.highpass(fs_, 20.f * powf(5000.f / 20.f, f), 0.8f);                    // 20 Hz -> 5 kHz
    }
    if (p.eq[0] != k.cEq[0]) { k.cEq[0] = p.eq[0]; k.eq[0].highShelf(fs_, EQ_HI_HZ, p.eq[0]); }
    if (p.eq[1] != k.cEq[1]) { k.cEq[1] = p.eq[1]; k.eq[1].peak(fs_, EQ_MID_HZ, EQ_MID_Q, p.eq[1]); }
    if (p.eq[2] != k.cEq[2]) { k.cEq[2] = p.eq[2]; k.eq[2].lowShelf(fs_, EQ_LO_HZ, p.eq[2]); }
    if (p.comp != k.cComp) { k.cComp = p.comp; k.comp.setAmount(p.comp); }
}

void Mixer::process(AudioIO& io) {
    const int n = io.n > MAX_BLOCK ? MAX_BLOCK : io.n;
    const float dt = (float)n / fs_;
    const float invN = 1.f / n;
    float mainL[MAX_BLOCK] = {}, mainR[MAX_BLOCK] = {}, auxL[MAX_BLOCK] = {}, auxR[MAX_BLOCK] = {};
    float cueL[MAX_BLOCK] = {}, cueR[MAX_BLOCK] = {};
    float fxL[NFX][MAX_BLOCK] = {}, fxR[NFX][MAX_BLOCK] = {};
    float l[MAX_BLOCK], r[MAX_BLOCK];
    static const float zero[MAX_BLOCK] = {};

    // USB to the DAW: inputs before processing (DM10)
    if (io.usbOutChannels >= 2 * NCH) {
        for (int i = 0; i < 2 * NCH; i++)
            if (io.usbOut[i]) memcpy(io.usbOut[i], io.in[i] ? io.in[i] : zero, n * sizeof(float));
    }

    for (int c = 0; c < NCH; c++) {
        updateChannel(c);
        Channel& k = ch_[c];
        const ChannelParams& p = s_->ch[c];
        const float* inL = io.in[2 * c] ? io.in[2 * c] : zero;
        const float* inR = io.in[2 * c + 1] ? io.in[2 * c + 1] : zero;
        const bool stereo = p.stereo;
        for (int i = 0; i < n; i++) {
            l[i] = inL[i];
            r[i] = stereo ? inR[i] : inL[i];        // mono: the tip only (a TS plug shorts the ring)
        }
        if (!k.flt.identity())
            for (int i = 0; i < n; i++) { l[i] = k.fltS[0].run(k.flt, l[i]); r[i] = k.fltS[1].run(k.flt, r[i]); }
        for (int b = 0; b < 3; b++)
            if (!k.eq[b].identity())
                for (int i = 0; i < n; i++) { l[i] = k.eqS[b][0].run(k.eq[b], l[i]); r[i] = k.eqS[b][1].run(k.eq[b], r[i]); }
        if (p.comp > 0.001f) {
            for (int i = 0; i < n; i++) k.comp.run(l[i], r[i]);
            chGr[c] = k.comp.grDb;
        } else chGr[c] = 0;
        if (stereo && p.width < 0.999f) {
            for (int i = 0; i < n; i++) {
                float m = 0.5f * (l[i] + r[i]), s = 0.5f * (l[i] - r[i]) * p.width;
                l[i] = m + s; r[i] = m - s;
            }
        }

        // clip mark: the ADC input itself at full scale (the float processing after it cannot clip)
        float inL0 = 0, inR0 = 0;
        for (int i = 0; i < n; i++) { inL0 = fmaxf(inL0, fabsf(inL[i])); inR0 = fmaxf(inR0, fabsf(inR[i])); }
        // cue: after processing, before mute and fader (PFL)
        if (p.cue)
            for (int i = 0; i < n; i++) { cueL[i] += l[i]; cueR[i] += r[i]; }

        // mute, fader, pan: per-block targets, linear ramps inside the block
        float g = p.mute ? 0.f : dbToLin(faderDb(l_->fader[c]));
        float tl, tr;
        if (stereo) {
            tl = p.pan > 0 ? 1.f - p.pan : 1.f;      // balance
            tr = p.pan < 0 ? 1.f + p.pan : 1.f;
        } else {
            float a = (p.pan + 1.f) * (kPi / 4);     // constant power, -3 dB in the centre
            tl = cosf(a); tr = sinf(a);
        }
        tl *= g; tr *= g;
        float dl = (tl - k.gl) * invN, dr = (tr - k.gr) * invN;
        float aux0 = k.sAux, dAux = (p.sendAux - aux0) * invN;
        float fx0[NFX], dFx[NFX];
        for (int f = 0; f < NFX; f++) { fx0[f] = k.sFx[f]; dFx[f] = (p.sendFx[f] - fx0[f]) * invN; }
        float gl = k.gl, gr = k.gr, pkL = 0, pkR = 0;
        for (int i = 0; i < n; i++) {
            gl += dl; gr += dr; aux0 += dAux;
            float ol = l[i] * gl, orr = r[i] * gr;
            pkL = fmaxf(pkL, fabsf(ol)); pkR = fmaxf(pkR, fabsf(orr));
            mainL[i] += ol; mainR[i] += orr;
            auxL[i] += ol * aux0; auxR[i] += orr * aux0;
            for (int f = 0; f < NFX; f++) {
                fx0[f] += dFx[f];
                fxL[f][i] += ol * fx0[f]; fxR[f][i] += orr * fx0[f];
            }
        }
        // channel meters: what the channel sends into the mix (after mute, fader, pan)
        chMeter[c][0].block(pkL, dt, inL0 >= 0.99f);
        chMeter[c][1].block(pkR, dt, (stereo ? inR0 : inL0) >= 0.99f);
        k.gl = tl; k.gr = tr; k.sAux = p.sendAux;
        for (int f = 0; f < NFX; f++) k.sFx[f] = p.sendFx[f];

        if (tunerChannel == c) {                     // decimate by 2 into the tuner ring
            uint32_t w = tunerWrite;
            for (int i = 0; i < n; i++)
                if (++tunerDecim_ & 1) tunerBuf[w++ % TUNER_LEN] = inL[i] + (stereo ? inR[i] : 0.f);
            tunerWrite = w;
        }
    }

    // FX buses -> MAIN
    float wetL[MAX_BLOCK], wetR[MAX_BLOCK];
    for (int f = 0; f < NFX; f++) {
        fx_[f].process(fxL[f], fxR[f], wetL, wetR, n, s_->fx[f], s_->bpm);
        float r0 = fxRet_[f], dRet = (s_->fx[f].ret - r0) * invN;
        for (int i = 0; i < n; i++) {
            r0 += dRet;
            mainL[i] += wetL[i] * r0; mainR[i] += wetR[i] * r0;
        }
        fxRet_[f] = s_->fx[f].ret;
    }

    // USB from the DAW -> MAIN
    {
        float tgt = dbToLin(s_->usbDb), g = gUsb_, d = (tgt - g) * invN;
        const float* ul = io.usbIn[0] ? io.usbIn[0] : zero;
        const float* ur = io.usbIn[1] ? io.usbIn[1] : zero;
        for (int i = 0; i < n; i++) { g += d; mainL[i] += ul[i] * g; mainR[i] += ur[i] * g; }
        gUsb_ = tgt;
    }

    // master stages
    float* oML = io.out[0]; float* oMR = io.out[1];
    float* oAL = io.out[2]; float* oAR = io.out[3];
    float* oPL = io.out[4]; float* oPR = io.out[5];
    float tMain = dbToLin(s_->mainDb), tAux = dbToLin(s_->auxDb), tPh = dbToLin(s_->phonesDb);
    float dMain = (tMain - gMain_) * invN, dAuxG = (tAux - gAux_) * invN, dPh = (tPh - gPh_) * invN;
    PhonesSrc src = (PhonesSrc)s_->phonesSrc;
    float cueTarget = src == PhonesSrc::Cue || (src == PhonesSrc::Auto && anyCue()) ? 1.f : 0.f;
    float dCue = (cueTarget - cueMix_) * invN;
    float pk[6] = {};
    for (int i = 0; i < n; i++) {
        gMain_ += dMain; gAux_ += dAuxG; gPh_ += dPh; cueMix_ += dCue;
        float ml = mainL[i] * gMain_, mr = mainR[i] * gMain_;
        if (s_->limiter) lim_.run(ml, mr);
        else { ml = safeClip(ml); mr = safeClip(mr); }
        float al = safeClip(auxL[i] * gAux_), ar = safeClip(auxR[i] * gAux_);
        float hl = (ml * (1.f - cueMix_) + cueL[i] * cueMix_) * gPh_;
        float hr = (mr * (1.f - cueMix_) + cueR[i] * cueMix_) * gPh_;
        hl = safeClip(hl); hr = safeClip(hr);
        if (oML) oML[i] = ml;
        if (oMR) oMR[i] = mr;
        if (oAL) oAL[i] = al;
        if (oAR) oAR[i] = ar;
        if (oPL) oPL[i] = hl;
        if (oPR) oPR[i] = hr;
        pk[0] = fmaxf(pk[0], fabsf(ml)); pk[1] = fmaxf(pk[1], fabsf(mr));
        pk[2] = fmaxf(pk[2], fabsf(al)); pk[3] = fmaxf(pk[3], fabsf(ar));
        pk[4] = fmaxf(pk[4], fabsf(hl)); pk[5] = fmaxf(pk[5], fabsf(hr));
    }
    gMain_ = tMain; gAux_ = tAux; gPh_ = tPh; cueMix_ = cueTarget;
    limGr = s_->limiter ? lim_.grDb : 0.f;
    for (int k = 0; k < 2; k++) {
        mainMeter[k].block(pk[k], dt);
        auxMeter[k].block(pk[2 + k], dt);
        phonesMeter[k].block(pk[4 + k], dt);
    }

    // stereo USB build: MAIN or one input pair
    if (io.usbOutChannels == 2) {
        int sel = usbSend;
        const float* a = sel >= 1 && sel <= NCH ? io.in[2 * (sel - 1)] : oML;
        const float* b = sel >= 1 && sel <= NCH ? io.in[2 * (sel - 1) + 1] : oMR;
        if (io.usbOut[0]) memcpy(io.usbOut[0], a ? a : zero, n * sizeof(float));
        if (io.usbOut[1]) memcpy(io.usbOut[1], b ? b : zero, n * sizeof(float));
    }

    if (recorder && recorder->active()) {
        const float* chans[2 * NCH + 2];
        int k = 0;
        if (recorder->channels() > 2)
            for (int i = 0; i < 2 * NCH; i++) chans[k++] = io.in[i];
        chans[k++] = oML;
        chans[k++] = oMR;
        recorder->write(chans, n);
    }
}
