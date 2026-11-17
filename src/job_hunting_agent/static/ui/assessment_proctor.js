/* Shared browser monitor for Mock Test and Mock Interview. Inference stays on device. */
(function () {
  'use strict';
  const VISION_URL = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.21/+esm';
  const WASM_URL = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.21/wasm';
  const FACE_MODEL = 'https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite';
  const OBJECT_MODEL = 'https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/float32/1/efficientdet_lite0.tflite';
  const NAMES = {
    tab_hidden: 'You switched away from the assessment tab.',
    fullscreen_exit: 'You left fullscreen mode.',
    camera_lost: 'The camera stopped.', microphone_lost: 'The microphone stopped.',
    face_absent: 'Your face was not visible for several seconds.',
    multiple_faces: 'More than one face was visible.',
    face_obscured: 'Your face is too far away or partly outside the camera view.',
    poor_lighting: 'Your face is difficult to see. Improve the lighting.',
    device_visible: 'A phone or another computer was visible in the camera view.'
  };

  class AssessmentProctor {
    constructor(video, onStatus, onPreview) {
      this.video = video;
      this.onStatus = onStatus || (() => {});
      this.onPreview = onPreview || (() => {});
      this.stream = null;
      this.kind = '';
      this.assessmentId = 0;
      this.active = false;
      this.busy = false;
      this.counts = {};
      this.incidents = {};
      this.pending = new Set();
      this.lastObjectCheck = -Infinity;
      this.canvas = document.createElement('canvas');
      this.canvas.width = 64;
      this.canvas.height = 48;
      this.dialog = document.createElement('div');
      this.dialog.className = 'assessment-proctor-dialog';
      this.dialog.hidden = true;
      this.dialog.innerHTML = '<section role="alertdialog" aria-modal="true" aria-label="Assessment monitoring"><h2 id="proctor-title"></h2><p id="proctor-message"></p><button type="button" id="proctor-continue">Continue</button><a id="proctor-dashboard" href="/" hidden>Return to Dashboard</a></section>';
      document.body.appendChild(this.dialog);
      this.dialog.querySelector('button').addEventListener('click', async () => {
        if (this.terminated) return;
        if (!document.fullscreenElement) {
          try { await document.documentElement.requestFullscreen(); }
          catch (_) { this.onStatus('Re-enter fullscreen to continue.'); return; }
        }
        this.dialog.hidden = true;
      });
      this.dialog.querySelector('#proctor-dashboard').addEventListener('click', async event => {
        event.preventDefault();
        try { if (document.fullscreenElement) await document.exitFullscreen(); }
        catch (_) { /* Navigation also exits fullscreen. */ }
        window.location.assign('/');
      });
      this.visibilityHandler = () => {
        if (this.active && document.visibilityState === 'hidden') this.signal('tab_hidden');
      };
      this.fullscreenHandler = () => {
        if (this.active && !document.fullscreenElement && document.visibilityState === 'visible') this.signal('fullscreen_exit');
      };
      document.addEventListener('visibilitychange', this.visibilityHandler);
      document.addEventListener('fullscreenchange', this.fullscreenHandler);
    }

    async enable() {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('Camera and microphone require HTTPS or localhost and a supported browser.');
      this.closeMedia();
      this.lastObjectCheck = -Infinity;
      this.lastDevices = false;
      this.stream = await navigator.mediaDevices.getUserMedia({video: {facingMode: 'user', width: {ideal: 640}}, audio: true});
      if (!this.stream.getVideoTracks().some(t => t.readyState === 'live') || !this.stream.getAudioTracks().some(t => t.readyState === 'live')) {
        this.closeMedia();
        throw new Error('Both camera and microphone must be enabled.');
      }
      this.video.srcObject = this.stream;
      await this.video.play();
      this.onPreview();
      this.onStatus('Camera and microphone connected. Checking your face and lighting...');
      await this.loadVision();
      await this.checkRoom();
      for (const track of this.stream.getTracks()) {
        track.addEventListener('ended', () => this.active && this.signal(track.kind === 'video' ? 'camera_lost' : 'microphone_lost'));
        track.addEventListener('mute', () => this.active && this.signal(track.kind === 'video' ? 'camera_lost' : 'microphone_lost'));
      }
      this.onStatus('Camera, microphone, face, and lighting checks passed. Click Start to enter fullscreen.');
    }

    async checkRoom() {
      // A camera can report that it is playing before its first usable frame arrives.
      const deadline = performance.now() + 6000;
      let goodFrames = 0;
      let lastCheck = {faces: 0, brightness: 0, faceArea: 0, devices: false};
      while (performance.now() < deadline) {
        if (!this.stream?.getTracks().every(t => t.readyState === 'live' && t.enabled)) {
          throw new Error('Camera or microphone disconnected. Reconnect it and check again.');
        }
        lastCheck = this.inspect();
        goodFrames = this.roomProblem(lastCheck) ? 0 : goodFrames + 1;
        if (goodFrames >= 2) return;
        await new Promise(resolve => setTimeout(resolve, 350));
      }
      throw new Error(this.roomProblem(lastCheck) + ' Keep the camera preview open, adjust your setup, then click Recheck Devices.');
    }

    roomProblem(check) {
      if (check.faces > 1) return 'More than one face is visible.';
      if (check.faces === 0) return 'No face detected. Face the camera and move into view.';
      if (check.faceArea < 0.025) return 'Your face is too far away or partly outside the camera view.';
      if (check.brightness < 35) return 'Your face is too dark. Add light in front of you.';
      if (check.devices) return 'A phone or another computer is visible. Remove it from view.';
      return '';
    }

    async loadVision() {
      if (this.faceDetector && this.objectDetector) return;
      const vision = await import(VISION_URL);
      const files = await vision.FilesetResolver.forVisionTasks(WASM_URL);
      this.faceDetector = await vision.FaceDetector.createFromOptions(files, {
        baseOptions: {modelAssetPath: FACE_MODEL}, runningMode: 'VIDEO', minDetectionConfidence: 0.55
      });
      this.objectDetector = await vision.ObjectDetector.createFromOptions(files, {
        baseOptions: {modelAssetPath: OBJECT_MODEL}, runningMode: 'VIDEO', scoreThreshold: 0.55, maxResults: 8
      });
    }

    inspect() {
      const video = this.video;
      if (!video.videoWidth || !video.videoHeight) return {faces: 0, brightness: 0, faceArea: 0, devices: false};
      const faces = this.faceDetector.detectForVideo(video, performance.now()).detections || [];
      const box = faces[0]?.boundingBox;
      const ctx = this.canvas.getContext('2d', {willReadFrequently: true});
      ctx.drawImage(video, 0, 0, 64, 48);
      const pixels = ctx.getImageData(0, 0, 64, 48).data;
      let light = 0;
      let samples = 0;
      const x0 = box ? Math.max(0, Math.floor(box.originX * 64 / video.videoWidth)) : 0;
      const y0 = box ? Math.max(0, Math.floor(box.originY * 48 / video.videoHeight)) : 0;
      const x1 = box ? Math.min(64, Math.ceil((box.originX + box.width) * 64 / video.videoWidth)) : 64;
      const y1 = box ? Math.min(48, Math.ceil((box.originY + box.height) * 48 / video.videoHeight)) : 48;
      for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) {
        const i = (y * 64 + x) * 4;
        light += (pixels[i] + pixels[i + 1] + pixels[i + 2]) / 3;
        samples++;
      }
      const brightness = samples ? light / samples : 0;
      const faceArea = box ? (box.width * box.height) / (video.videoWidth * video.videoHeight) : 0;
      let devices = this.lastDevices || false;
      if (performance.now() - this.lastObjectCheck > 2500) {
        this.lastObjectCheck = performance.now();
        const objects = this.objectDetector.detectForVideo(video, performance.now()).detections || [];
        devices = objects.some(o => o.categories?.some(c => ['cell phone', 'laptop', 'tablet', 'tv'].includes(c.categoryName?.toLowerCase()) && c.score >= 0.55));
        this.lastDevices = devices;
      }
      return {faces: faces.length, brightness, faceArea, devices};
    }

    async enterFullscreen() {
      if (!this.stream || !this.stream.getTracks().every(t => t.readyState === 'live' && t.enabled)) {
        throw new Error('Enable both camera and microphone before starting.');
      }
      await document.documentElement.requestFullscreen();
      if (!document.fullscreenElement) throw new Error('Fullscreen is required.');
    }

    activate(kind, assessmentId) {
      this.kind = kind;
      this.assessmentId = assessmentId;
      this.active = true;
      this.terminated = false;
      this.monitor = setInterval(() => this.sample(), 1200);
      this.heartbeatTimer = setInterval(() => this.heartbeat(), 10000);
      this.heartbeat();
    }

    sample() {
      if (!this.active || this.busy || document.visibilityState === 'hidden') return;
      if (!this.stream?.getTracks().every(t => t.readyState === 'live' && t.enabled)) {
        this.observe('camera_lost', true, 2); return;
      }
      this.busy = true;
      try {
        const frame = this.inspect();
        this.observe('multiple_faces', frame.faces > 1, 2);
        this.observe('face_absent', frame.faces === 0, 4);
        this.observe('face_obscured', frame.faces === 1 && frame.faceArea < 0.025, 5);
        this.observe('poor_lighting', frame.brightness < 35, 7);
        this.observe('device_visible', frame.devices, 2);
      } catch (_) { this.onStatus('Video check interrupted; keep the camera available.'); }
      finally { this.busy = false; }
    }

    observe(name, present, threshold) {
      this.counts[name] = present ? (this.counts[name] || 0) + 1 : 0;
      if (!present) this.incidents[name] = false;
      if (this.counts[name] >= threshold && !this.incidents[name]) {
        this.incidents[name] = true;
        this.signal(name);
      }
    }

    async signal(signal) {
      if (!this.active || this.pending.has(signal)) return;
      this.pending.add(signal);
      try {
        const response = await fetch('/api/proctor/event', {method: 'POST', credentials: 'same-origin',
          headers: {'Content-Type': 'application/json'}, keepalive: true,
          body: JSON.stringify({kind: this.kind, assessment_id: this.assessmentId, signal, event_id: crypto.randomUUID()})});
        if (response.ok) this.applyState(await response.json(), signal);
        else this.onStatus('Monitoring connection failed; attempting to reconnect.');
      } catch (_) { this.onStatus('Monitoring connection failed; attempting to reconnect.'); }
      finally { this.pending.delete(signal); }
    }

    async heartbeat() {
      if (!this.active) return;
      try {
        const response = await fetch('/api/proctor/heartbeat', {method: 'POST', credentials: 'same-origin',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({kind: this.kind, assessment_id: this.assessmentId})});
        if (response.ok) this.applyState(await response.json());
      } catch (_) { this.onStatus('Monitoring connection interrupted. Reconnect within one minute.'); }
    }

    applyState(state, signal) {
      if (state.status === 'terminated') {
        this.terminated = true;
        this.active = false;
        clearInterval(this.monitor); clearInterval(this.heartbeatTimer);
        this.show('Assessment stopped', state.reason || 'The assessment is no longer active.', true);
        this.closeMedia();
        this.onStatus('terminated');
      } else if (state.action === 'warning') {
        this.show(`Warning ${state.warnings} of 2`, `${NAMES[signal] || 'A monitoring issue occurred'} A third confirmed violation will stop this assessment.`, false);
        this.onStatus(`Warning ${state.warnings} of 2: ${NAMES[signal] || signal}`);
      }
    }

    show(title, message, terminal) {
      this.dialog.querySelector('#proctor-title').textContent = title;
      this.dialog.querySelector('#proctor-message').textContent = message;
      this.dialog.querySelector('button').hidden = terminal;
      this.dialog.querySelector('#proctor-dashboard').hidden = !terminal;
      this.dialog.hidden = false;
    }

    closeMedia() {
      if (this.stream) this.stream.getTracks().forEach(t => t.stop());
      this.stream = null;
      this.video.srcObject = null;
    }

    stop() {
      this.active = false;
      clearInterval(this.monitor); clearInterval(this.heartbeatTimer);
      this.closeMedia();
      if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    }
  }

  window.AssessmentProctor = AssessmentProctor;
})();
