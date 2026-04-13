import { useState, useEffect, useRef } from 'react';
import {
  View, Text, TouchableOpacity,
  StyleSheet, Vibration, SafeAreaView
} from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import * as Speech from 'expo-speech';
import axios from 'axios';

// 🔴 CHANGE THIS to your PC's IP address
const SERVER_URL = 'http://10.126.151.35:5000';

export default function App() {
  const [permission, requestPermission] = useCameraPermissions();
  const [status, setStatus] = useState('VisionAid Ready');
  const [isProcessing, setIsProcessing] = useState(false);
  const [findObject] = useState('chair');
  const [autoDetect, setAutoDetect] = useState(false);
  const cameraRef = useRef(null);
  const autoDetectRef = useRef(null);

  useEffect(() => {
    speak('VisionAid ready. Tap a button to begin.');
    return () => {
      if (autoDetectRef.current) {
        clearInterval(autoDetectRef.current);
      }
    };
  }, []);

  // ── Speak helper ──────────────────────────────────────────
  const speak = (text) => {
    Speech.stop();
    Speech.speak(text, {
      rate: 0.9,
      pitch: 1.0,
      language: 'en-US'
    });
    setStatus(text);
  };

  // ── Capture photo and send to server ─────────────────────
  const captureAndSend = async (action, extra = {}) => {
    if (!cameraRef.current || isProcessing) return;

    try {
      setIsProcessing(true);
      speak('Processing...');

      const photo = await cameraRef.current.takePictureAsync({
        quality: 0.5,
        base64: true,
        skipProcessing: true
      });

      const response = await axios.post(`${SERVER_URL}/${action}`, {
        image: photo.base64,
        ...extra
      }, { timeout: 30000 });

      const result = response.data.result;

      if (action === 'navigate' && result.startsWith('WARNING')) {
        Vibration.vibrate([500, 200, 500]);
      }

      speak(result);

    } catch (error) {
      if (error.code === 'ECONNREFUSED') {
        speak('Cannot connect to server. Make sure server is running.');
      } else if (error.code === 'ETIMEDOUT') {
        speak('Server took too long. Please try again.');
      } else {
        speak('Something went wrong. Please try again.');
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
            quality: 0.3,
            base64: true,
            skipProcessing: true
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
          // Silent fail for auto detection
          console.error('Auto detect error:', error);
        }
      }, 5000); // every 5 seconds
    }, 2000); // wait 2 seconds before starting
  };

  const stopAutoDetect = () => {
    if (autoDetectRef.current) {
      clearInterval(autoDetectRef.current);
      autoDetectRef.current = null;
    }
    setAutoDetect(false);
    speak('Auto detection stopped.');
  };

  if (!permission) return <View style={styles.container} />;

  if (!permission.granted) {
    return (
      <SafeAreaView style={styles.container}>
        <Text style={styles.permissionText}>
          Camera permission is required for VisionAid to work.
        </Text>
        <TouchableOpacity style={styles.permissionBtn} onPress={requestPermission}>
          <Text style={styles.btnText}>Grant Camera Permission</Text>
        </TouchableOpacity>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>

      {/* Camera */}
      <CameraView style={styles.camera} facing="back" ref={cameraRef} />

      {/* Status bar */}
      <View style={styles.statusBar}>
        <Text style={styles.statusText} numberOfLines={3}>
          {isProcessing ? '⏳ Processing...' :
           autoDetect ? '🔄 ' + status : status}
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

        {/* Stop — big and visible */}
        <TouchableOpacity
          style={styles.stopBtn}
          onPress={() => {
            Speech.stop();
            stopAutoDetect();
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
    padding: 12,
    minHeight: 70,
    justifyContent: 'center'
  },
  statusText: {
    color: 'white', fontSize: 14,
    textAlign: 'center', lineHeight: 20
  },
  controls: {
    backgroundColor: '#111',
    padding: 12,
    paddingBottom: 20
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 10
  },
  btn: {
    flex: 1, marginHorizontal: 5,
    padding: 14, borderRadius: 12,
    alignItems: 'center', justifyContent: 'center'
  },
  btnDisabled: { opacity: 0.4 },
  btnBlue:     { backgroundColor: '#2196F3' },
  btnGreen:    { backgroundColor: '#4CAF50' },
  btnOrange:   { backgroundColor: '#FF9800' },
  btnPurple:   { backgroundColor: '#9C27B0' },
  btnTeal:     { backgroundColor: '#009688' },
  btnDarkTeal: { backgroundColor: '#00695C' },
  btnRed:      { backgroundColor: '#F44336' },
  btnIcon: { fontSize: 24, marginBottom: 4 },
  btnText: { color: 'white', fontWeight: 'bold', fontSize: 13 },
  stopBtn: {
    backgroundColor: '#F44336',
    padding: 18,
    borderRadius: 12,
    alignItems: 'center',
    marginHorizontal: 5,
    marginTop: 5,
    flexDirection: 'row',
    justifyContent: 'center'
  },
  stopIcon: { fontSize: 28, marginRight: 10 },
  stopText: { color: 'white', fontWeight: 'bold', fontSize: 18 },
  permissionText: {
    color: 'white', textAlign: 'center',
    fontSize: 16, margin: 30
  },
  permissionBtn: {
    backgroundColor: '#2196F3',
    padding: 15, borderRadius: 10,
    margin: 20, alignItems: 'center'
  }
});