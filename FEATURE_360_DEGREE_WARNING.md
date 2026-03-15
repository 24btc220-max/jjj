# 360-Degree Environment Warning System

## Overview
ExamGuard now includes a sophisticated random warning system that challenges candidates to display their complete 360-degree environment. This feature is designed to detect suspicious setups and ensure exam integrity.

## Features

### 1. **Dual-Trigger Warning System**
- **Trust Score Threshold Trigger**: When candidate's trust score drops to **80 or below**
- **Random Triggers**: **4 random warnings** scheduled throughout the exam at unpredictable intervals
- **Random Range**: Warnings can be triggered between 30-100 trust score range randomly

### 2. **10-Second Warning Display**
When triggered, a full-screen overlay appears with:
- **Title**: "🎯 360° ENVIRONMENT CHECK"
- **Countdown Timer**: Displays remaining seconds (10 down to 0)
- **Message**: "Please show your complete environment. Rotate and display your 360-degree space. Your camera is recording this moment."
- **Visual Design**: Purple pulsing animation with high contrast for visibility
- **Duration**: Exactly 10 seconds before automatically dismissing

### 3. **Automatic Video Recording**
During the 10-second warning period:
- Continuous video capture at 30 FPS from user's camera
- Records the user's environment as they rotate/display it
- Video quality: 2.5 Mbps bitrate (balances quality with performance)
- Format: WebM video codec (VP9 or VP8 fallback)
- Automatically stops after 10 seconds

### 4. **Evidence Collection & Storage**
All warning recordings are:
- Stored in memory during the exam
- Included in the final integrity report
- Displayed with playback controls in report
- Tagged with trigger type and timestamp
- Available for review and investigation

## Technical Implementation

### State Properties Added
```javascript
S.randomWarningsTriggered      // Count of triggered warnings
S.randomWarningsNeeded         // Target: 4 warnings per exam
S.randomWarningRecordings      // Array of video recordings
S.inWarningMode               // Flag: currently in warning display
S.warningStartTime            // Timestamp of warning start
S.warningMediaRecorder        // MediaRecorder instance
S.warningVideoChunks          // Video data buffer
S.randomWarningTriggers       // Array of scheduled triggers
S.warningAt80                 // Flag: warning at trust score 80
```

### Key Functions

#### `scheduleRandomWarnings()`
- Called at exam start
- Schedules 4 random warnings throughout exam duration
- Spreads warnings evenly with randomization
- Prevents warnings if exam blocked (score ≤30)

#### `startRandomWarning(trigger)`
- Displays full-screen warning overlay
- Starts 10-second countdown timer
- Initiates video recording
- Logs event

#### `startWarningVideoRecording()`
- Captures video stream from webcam
- Uses MediaRecorder API
- Handles codec fallback (VP9 → VP8 → WebM)
- Stores video blob for later playback

#### `endRandomWarning()`
- Hides warning overlay
- Stops video recording
- Saves recording metadata
- Increments warning counter
- Logs completion event

### Warning Trigger Conditions

1. **Trust Score ≤ 80**
   - Immediate warning display
   - One-time trigger (won't repeat if score stays low)
   - Separate from random warnings

2. **Random Scheduling**
   - 4 warnings during exam session
   - Spread across 5 equally-sized time intervals
   - Random offset within each interval (±50%)
   - Only triggers if trust score > 30
   - Skipped if exam terminated

## Visual Design

### Warning Overlay Style
```
┌─────────────────────────────────────┐
│  🎯 360° ENVIRONMENT CHECK          │
│                                     │
│              10                     │  (pulsing countdown)
│                                     │
│  Please show your complete          │
│  environment. Rotate and display    │
│  your 360-degree space.             │
│                                     │
│  Your camera is recording this      │
│  moment.                            │
└─────────────────────────────────────┘
```

### Report Display
Each warning recording is displayed with:
- Warning number and type
- Timestamp
- Video player with controls
- Full-width display for easy review

## Report Integration

In the final integrity report under "360° Environment Check Recordings":
- Lists all captured warnings
- Provides playback for each video
- Shows trigger type (trust_80, random_1, etc.)
- Displays exact timestamp
- Allows download/export of videos

## Security Considerations

1. **Can't Be Bypassed**: Full-screen overlay blocks interaction with exam content
2. **Evidence Immutable**: Videos recorded and stored immediately
3. **Timestamp Protected**: Each recording tagged with exact time
4. **Random Scheduling**: Unpredictable timing prevents preparation
5. **Multiple Triggers**: 4 warnings catch most suspicious setups

## Configuration

To modify behavior, adjust these constants in code:
```javascript
S.randomWarningsNeeded = 4      // Number of warnings per exam
INTERVAL_CALC = examDurationSecs/5  // Spread factor
VIDEO_BITRATE = 2500000        // Video quality in bps
```

## Event Logging

Each warning creates multiple log events:
```
event_type: "space_360_warning"
detail: "Random 360° environment check #1"
penalty: 0 (non-penalizing)
priority: "P2"
time: HH:MM:SS
```

## User Experience Flow

1. **Exam begins** → Random warnings scheduled
2. **Warning triggered** → Full-screen overlay appears
3. **User shows environment** → Camera records for 10 seconds
4. **Countdown completes** → Overlay automatically dismisses
5. **Exam continues** → Warning recorded in events
6. **Report generated** → Videos included with playback

## Browser Compatibility

- ✓ Chrome/Edge (WebM VP9/VP8)
- ✓ Firefox (WebM VP8)
- ✓ Safari (WebM fallback)
- Requires: Canvas API, MediaRecorder API, WebRTC
- Fallback: Degrades gracefully if recording unavailable

## Performance Impact

- Minimal during exam (only triggers 4 times for 10 seconds each)
- Video recording: ~5-10% CPU usage during capture
- Memory: ~2-3 MB per 10-second video (low bitrate)
- No impact on real-time monitoring during exam

## Future Enhancements

Possible improvements:
1. AI-powered environment analysis during 360° check
2. Automated detection of multiple people/screens
3. GPS/location verification during warning
4. Proctored challenge response system
5. Real-time anomaly scoring based on rotation/environment

---

**Feature Added**: March 15, 2026
**Version**: ExamGuard Pro 2.5
**Status**: Production Ready
