import { useState, useEffect, useRef } from 'react';
import {
  View, Text, TouchableOpacity,
  StyleSheet, Vibration, SafeAreaView
} from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import * as Speech from 'expo-speech';
import axios from 'axios';
import {
  ExpoSpeechRecognitionModule,
  useSpeechRecognitionEvent
} from 'expo-speech-recognition';

// 🔴 CHANGE THIS to your server URL
const SERVER_URL = 'http://10.126.151.35:5000';

// Wake words that activate the app
const WAKE_WORDS = ['hey vision', 'hi vision', 'okay vision', 'vision'];

export default function App() {
  const [permission, requestPermission] = useCameraPermissions();
  const [status, setStatus] = useState('VisionAid Ready');
  const [isProcessing, setIsProcessing] = useState(false);
  const [findObject] = useState('chair');
  const [autoDetect, setAutoDetect] = useState(false);
  const [isOnline, setIsOnline] = useState(true);
  const [isListening, setIsListening] = useState(false);
  const [isWakeMode, setIsWakeMode] = useState(false);
  const cameraRef = useRef(null);
  const autoDetectRef = useRef(null);
  const wakeLoopRef = useRef(null);

  useEffect(() => {
    speak('VisionAid ready. Tap a button or say Hey Vision to begin.');
    checkConnection();
    const interval = setInterval(checkConnection, 30000);
    return () => {
      clearInterval(interval);
      if (autoDetectRef.current) clearInterval(autoDetectRef.current);
      stopWakeWord();
    };
  }, []);

  // ── Speech recognition events ─────────────────────────────
  useSpeechRecognitionEvent('start', () => setIsListening(true));
  useSpeechRecognitionEvent('end', () => {
    setIsListening(false);
    // If in wake mode, restart listening automatically
    if (wakeLoopRef.current) {
      setTimeout(() => startListeningOnce(), 500);
    }
  });
  useSpeechRecognitionEvent('result', (event) => {
    const text = (event.results[0]?.transcript || '').toLowerCase().trim();
    if (!text) return;

    if (wakeLoopRef.current) {
      // In wake word mode — check for wake word
      const woken = WAKE_WORDS.some(w => text.includes(w));
      if (woken) {
        Vibration.vibrate(200);
        speak('Yes? Say your command.');
        wakeLoopRef.current = false; // pause wake loop
        setTimeout(() => startListeningOnce(), 1000);
      }
    } else {
      // In command mode
      handleVoiceCommand(text);
      // Resume wake word mode after command
      setTimeout(() => {
        if (isWakeMode) {
          wakeLoopRef.current = true;
          startListeningOnce();
        }
      }, 3000);
    }
  });
  useSpeechRecognitionEvent('error', () => {
    setIsListening(false);
    if (wakeLoopRef.current) {
      setTimeout(() => startListeningOnce(), 1000);
    }
  });

  // ── Check internet connection ─────────────────────────────
  const checkConnection = async () => {
    try {
      const response = await axios.get(`${SERVER_URL}/status`, { timeout: 3000 });
      setIsOnline(response.data.online);
    } catch {
      setIsOnline(false);
    }
  };

  // ── Speak helper ──────────────────────────────────────────
  const speak = (text) => {
    Speech.stop();
    Speech.speak(text, { rate: 0.9, pitch: 1.0, language: 'en-US' });
    setStatus(text);
  };

  // ── Capture and send to server ────────────────────────────
  const captureAndSend = async (action, extra = {}) => {
    if (!cameraRef.current || isProcessing) return;
    try {
      setIsProcessing(true);
      speak('Processing...');
      const photo = await cameraRef.current.takePictureAsync({
        quality: 0.5, base64: true, skipProcessing: true
      });
      const response = await axios.post(`${SERVER_URL}/${action}`, {
        image: photo.base64, ...extra
      }, { timeout: 30000 });
      const result = response.data.result;
      if (action === 'navigate' && result.startsWith('WARNING')) {
        Vibration.vibrate([500, 200, 500]);
      }
      speak(result);
    } catch (error) {
      if (error.code === 'ECONNREFUSED') {
        speak('Cannot connect to server.');
      } else if (error.code === 'ETIMEDOUT') {
        speak('Server took too long. Try again.');
      } else {
        speak('Something went wrong. Try again.');
      }
      console.error(error);
    } finally {
      setIsProcessing(false);
    }
  };

  // ── Auto obstacle detection ───────────────────────────────
  const startAutoDetect = () => {
    if (autoDetectRef.current) return;
    setAutoDetect(true);
    speak('Auto detection started.');
    setTimeout(() => {
      autoDetectRef.current = setInterval(async () => {
        if (!cameraRef.current) return;
        try {
          const photo = await cameraRef.current.takePictureAsync({
            quality: 0.3, base64: true, skipProcessing: true
          });
          const response = await axios.post(`${SERVER_URL}/detect`, {
            image: photo.base64
          }, { timeout: 15000 });
          const result = response.data.result;
          if (result && result !== 'No objects detected in the scene') {
            if (result.includes('very close')) {
              Vibration.vibrate([300, 100, 300, 100, 300]);
              speak('Warning! ' + result);
            } else {
              speak(result);
            }
          }
        } catch (error) {
          console.error('Auto detect error:', error);
        }
      }, 5000);
    }, 2000);
  };

  const stopAutoDetect = () => {
    if (autoDetectRef.current) {
      clearInterval(autoDetectRef.current);
      autoDetectRef.current = null;
    }
    setAutoDetect(false);
    speak('Auto detection stopped.');
  };

  // ── Voice command handler ─────────────────────────────────
  const handleVoiceCommand = (text) => {
    setStatus(`Heard: "${text}"`);

    if (text.includes('stop') || text.includes('quiet')) {
      Speech.stop();
      stopAutoDetect();
      setStatus('Stopped.');
      return;
    }
    if (text.includes('describe') || text.includes('what') ||
        text.includes('see') || text.includes('around')) {
      captureAndSend('describe');
    } else if (text.includes('read') || text.includes('text')) {
      captureAndSend('read');
    } else if (text.includes('navigate') || text.includes('path') ||
               text.includes('walk') || text.includes('safe')) {
      captureAndSend('navigate');
    } else if (text.includes('detect') || text.includes('objects')) {
      captureAndSend('detect');
    } else if (text.includes('find') || text.includes('where is')) {
      const match = text.match(/find (.+)|where is (.+)/);
      const object = match ? (match[1] || match[2]).trim() : 'object';
      captureAndSend('find', { object });
    } else if (text.includes('auto')) {
      autoDetect ? stopAutoDetect() : startAutoDetect();
    } else {
      speak('Command not understood. Say describe, read, navigate, find, or detect.');
    }
  };

  // ── Single listen session ─────────────────────────────────
  const startListeningOnce = async () => {
    try {
      await ExpoSpeechRecognitionModule.start({
        lang: 'en-US',
        interimResults: false,
        continuous: false,
      });
    } catch (error) {
      console.error('Listen error:', error);
    }
  };

  // ── Manual voice button ───────────────────────────────────
  const startManualListen = async () => {
    if (isListening) {
      ExpoSpeechRecognitionModule.stop();
      return;
    }
    try {
      const { granted } = await ExpoSpeechRecognitionModule.requestPermissionsAsync();
      if (!granted) {
        speak('Microphone permission denied.');
        return;
      }
      wakeLoopRef.current = false; // command mode directly
      await startListeningOnce();
    } catch (error) {
      speak('Could not start voice recognition.');
    }
  };

  // ── Wake word mode ────────────────────────────────────────
  const startWakeWord = async () => {
    try {
      const { granted } = await ExpoSpeechRecognitionModule.requestPermissionsAsync();
      if (!granted) {
        speak('Microphone permission denied.');
        return;
      }
      setIsWakeMode(true);
      wakeLoopRef.current = true;
      speak('Wake word mode on. Say Hey Vision to activate.');
      await startListeningOnce();
    } catch (error) {
      speak('Could not start wake word mode.');
    }
  };

  const stopWakeWord = () => {
    wakeLoopRef.current = false;
    setIsWakeMode(false);
    try { ExpoSpeechRecognitionModule.stop(); } catch {}
    speak('Wake word mode off.');
  };

  if (!permission) return <View style={styles.container} />;

  if (!permission.granted) {
    return (
      <SafeAreaView style={styles.container}>
        <Text style={styles.permissionText}>Camera permission required.</Text>
        <TouchableOpacity style={styles.permissionBtn} onPress={requestPermission}>
          <Text style={styles.btnText}>Grant Permission</Text>
        </TouchableOpacity>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <CameraView style={styles.camera} facing="back" ref={cameraRef} />

      {/* Status bar */}
      <View style={styles.statusBar}>
        <Text style={styles.connectionText}>
          {isOnline ? '🟢 Online' : '🔴 Offline'}
          {isWakeMode ? '  |  👂 Listening for "Hey Vision"' : ''}
        </Text>
        <Text style={styles.statusText} numberOfLines={3}>
          {isProcessing ? '⏳ Processing...' :
           isListening  ? '🎤 Listening...' :
           autoDetect   ? '🔄 ' + status : status}
        </Text>
      </View>

      {/* Controls */}
      <View style={styles.controls}>

        {/* Row 1 */}
        <View style={styles.row}>
          <TouchableOpacity
            style={[styles.btn, styles.btnBlue, isProcessing && styles.btnDisabled]}
            onPress={() => captureAndSend('describe')}
            disabled={isProcessing}
          >
            <Text style={styles.btnIcon}>👁️</Text>
            <Text style={styles.btnText}>Describe</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.btn, styles.btnGreen, isProcessing && styles.btnDisabled]}
            onPress={() => captureAndSend('read')}
            disabled={isProcessing}
          >
            <Text style={styles.btnIcon}>📖</Text>
            <Text style={styles.btnText}>Read Text</Text>
          </TouchableOpacity>
        </View>

        {/* Row 2 */}
        <View style={styles.row}>
          <TouchableOpacity
            style={[styles.btn, styles.btnOrange, isProcessing && styles.btnDisabled]}
            onPress={() => captureAndSend('navigate')}
            disabled={isProcessing}
          >
            <Text style={styles.btnIcon}>🧭</Text>
            <Text style={styles.btnText}>Navigate</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.btn, styles.btnPurple, isProcessing && styles.btnDisabled]}
            onPress={() => captureAndSend('find', { object: findObject })}
            disabled={isProcessing}
          >
            <Text style={styles.btnIcon}>🔍</Text>
            <Text style={styles.btnText}>Find {findObject}</Text>
          </TouchableOpacity>
        </View>

        {/* Row 3 */}
        <View style={styles.row}>
          <TouchableOpacity
            style={[styles.btn, styles.btnTeal, isProcessing && styles.btnDisabled]}
            onPress={() => captureAndSend('detect')}
            disabled={isProcessing}
          >
            <Text style={styles.btnIcon}>🎯</Text>
            <Text style={styles.btnText}>Detect Once</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.btn, autoDetect ? styles.btnRed : styles.btnDarkTeal]}
            onPress={autoDetect ? stopAutoDetect : startAutoDetect}
          >
            <Text style={styles.btnIcon}>{autoDetect ? '⏹️' : '🔄'}</Text>
            <Text style={styles.btnText}>{autoDetect ? 'Stop Auto' : 'Auto Detect'}</Text>
          </TouchableOpacity>
        </View>

        {/* Row 4 — Voice */}
        <View style={styles.row}>
          <TouchableOpacity
            style={[styles.btn, isListening ? styles.btnRed : styles.btnVoice]}
            onPress={startManualListen}
          >
            <Text style={styles.btnIcon}>{isListening ? '⏹️' : '🎤'}</Text>
            <Text style={styles.btnText}>{isListening ? 'Stop' : 'Voice Command'}</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.btn, isWakeMode ? styles.btnRed : styles.btnWake]}
            onPress={isWakeMode ? stopWakeWord : startWakeWord}
          >
            <Text style={styles.btnIcon}>{isWakeMode ? '🔇' : '👂'}</Text>
            <Text style={styles.btnText}>{isWakeMode ? 'Stop Wake' : 'Hey Vision'}</Text>
          </TouchableOpacity>
        </View>

        {/* Stop */}
        <TouchableOpacity
          style={styles.stopBtn}
          onPress={() => {
            Speech.stop();
            stopAutoDetect();
            stopWakeWord();
            setStatus('Stopped.');
            setIsProcessing(false);
          }}
        >
          <Text style={styles.stopIcon}>🛑</Text>
          <Text style={styles.stopText}>STOP SPEAKING</Text>
        </TouchableOpacity>

      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000' },
  camera: { flex: 1 },
  statusBar: {
    backgroundColor: 'rgba(0,0,0,0.85)',
    padding: 12, minHeight: 80, justifyContent: 'center'
  },
  connectionText: { color: '#aaa', fontSize: 11, textAlign: 'center', marginBottom: 4 },
  statusText: { color: 'white', fontSize: 14, textAlign: 'center', lineHeight: 20 },
  controls: { backgroundColor: '#111', padding: 12, paddingBottom: 20 },
  row: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 10 },
  btn: {
    flex: 1, marginHorizontal: 5, padding: 14,
    borderRadius: 12, alignItems: 'center', justifyContent: 'center'
  },
  btnDisabled: { opacity: 0.4 },
  btnBlue:     { backgroundColor: '#2196F3' },
  btnGreen:    { backgroundColor: '#4CAF50' },
  btnOrange:   { backgroundColor: '#FF9800' },
  btnPurple:   { backgroundColor: '#9C27B0' },
  btnTeal:     { backgroundColor: '#009688' },
  btnDarkTeal: { backgroundColor: '#00695C' },
  btnRed:      { backgroundColor: '#F44336' },
  btnVoice:    { backgroundColor: '#1565C0' },
  btnWake:     { backgroundColor: '#6A1B9A' },
  btnIcon: { fontSize: 24, marginBottom: 4 },
  btnText: { color: 'white', fontWeight: 'bold', fontSize: 13 },
  stopBtn: {
    backgroundColor: '#F44336', padding: 18, borderRadius: 12,
    alignItems: 'center', marginHorizontal: 5, marginTop: 5,
    flexDirection: 'row', justifyContent: 'center'
  },
  stopIcon: { fontSize: 28, marginRight: 10 },
  stopText: { color: 'white', fontWeight: 'bold', fontSize: 18 },
  permissionText: { color: 'white', textAlign: 'center', fontSize: 16, margin: 30 },
  permissionBtn: {
    backgroundColor: '#2196F3', padding: 15,
    borderRadius: 10, margin: 20, alignItems: 'center'
  }
});