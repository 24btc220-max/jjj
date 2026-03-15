# 360-Degree Integrity Warning System

## Overview
The **360-Degree Integrity Warning System** is a random environmental verification feature that periodically prompts candidates to show their complete surroundings during exams, ensuring a clean test environment.

## Features

### 1. **Smart Scheduling**
- **No warnings in first 20% of exam**: Allows candidates to settle in
- **4 random warnings total** per exam session
- **Evenly distributed** across remaining 80% of exam time
- **±30% time variation** for unpredictability

### 2. **Random Triggering**
- Warnings are triggered **completely randomly** within calculated time windows
- Can trigger **between any trust score 30-100**
- Especially important when **trust score approaches 80** for suspicious activity
- Independent of candidate behavior (purely time-based)

### 3. **10-Second Video Recording**
- When warning triggers, displays **"Show Your 360° Space"** message for 10 seconds
- **Automatically records video frames** at ~5fps during the warning period
- Captures candidate's environment rotation
- Records ~50 frames per warning event

### 4. **Visual Warning Display**
- **Animated orange/amber modal** with pulsing effects
- **Countdown timer** showing remaining seconds
- **Progress bar** indicating time remaining
- **Clear instructions**: "Move your camera to show your complete surroundings"
- **Recording indicator** showing video capture is active

### 5. **Event Logging**
- Each warning logged as `warning_360` event type
- Stored with:
  - Warning number (1-4)
  - Timestamp
  - Trust score at trigger time
  - 50 recorded video frames

## Implementation Details

### State Management
```javascript
S.warning360Fired    // Count of warnings shown (0-4)
S.warning360Max      // Maximum warnings per exam (4)
S.warning360Active   // Currently showing warning
S.warning360RecordedFrames // Array of recorded frame data
```

### Warning Scheduling Algorithm
```
Exam Duration: T seconds
First Phase: 20% of T (no warnings)
Remaining: 80% of T (warning phase)
Interval: (Remaining / (Max + 1)) seconds
For each warning i (1-4):
  ScheduledTime = FirstPhaseEnd + (i × Interval) + RandomOffset
  RandomOffset = ±30% of Interval
```

### Example 45-min Exam Schedule
- **First 9 minutes**: No warnings (20% of 2700s)
- **Remaining 36 minutes**: 4 random warnings
- **Interval**: ~270 seconds between warning windows
- **Example times**: ~540s, ~810s, ~1080s, ~1350s (±30% variation)

## User Experience

### During Exam
1. Candidate is working on exam questions
2. At random scheduled time, orange warning modal appears
3. Candidate reads: "Show Your 360° Space"
4. Candidate rotates camera to show:
   - Front (face toward camera)
   - Left side of desk/room
   - Back (behind candidate)
   - Right side of desk/room
5. Camera records their environment for 10 seconds
6. Modal automatically closes
7. Candidate continues exam

### Recording Captured
- 50 JPEG frames at ~5fps
- Shows complete environmental rotation
- Used for post-exam integrity review
- Stored in report as `warning_360_video_${number}`

## Report Integration

### In Final Report
- Shows "360° Integrity Checks" section
- Displays all 4 warning timestamps
- Shows number of frames captured for each
- Can review recorded frames in full-screen modal
- Included in download JSON report

### Event Timeline
- Each 360° warning logged as separate event
- Shows timestamp and trust score at trigger time
- Marked as "Priority P2" (medium importance)
- No trust score penalty (informational event)

## Trust Score Context
- Warnings trigger **regardless of trust score** (purely time-based)
- But provide additional evidence if trust score **is suspicious**:
  - Trust score ~80 (warning zone): Environmental check adds confidence
  - Trust score <50 (critical): Multiple warning recordings show candidate attempted cheating setup
  - Trust score >85 (safe): Clean environment recordings support legitimacy claim

## Technical Implementation

### Modal Styling
- Beautiful gradient orange background (#fbbf24 → #f59e0b)
- Animated pulsing effect on the box
- 3px dark orange border
- Rotating 360° icon animation
- Large 48px countdown timer
- Progress bar animation showing time progress

### Frame Capture
- Records from exam video stream
- 320×240 canvas for efficient storage
- JPEG quality 0.6 for balance of quality/size
- ~50 frames per 10-second warning (~150KB total per warning)

### Integration Points
- **Exam Timer**: Check every second if warning should trigger
- **Video Stream**: Capture frames from live exam video
- **Event Log**: Log each warning as structured event
- **Report**: Display recorded frames in gallery
- **JSON Export**: Include all frames in downloadable report

## Configuration

### Adjustable Parameters
```javascript
S.warning360Max = 4;  // Number of warnings (default: 4)
S.timerSecs = 45*60;  // Exam duration in seconds (default: 45 min)
```

### Hardcoded Thresholds
- First phase: 20% of exam duration
- Recording frame rate: ~5fps (every 200ms)
- Recording duration: 10 seconds
- Time window tolerance: ±2 seconds
- Random offset: ±30% of interval

## Future Enhancements

### Possible Improvements
1. **AI-powered face detection** during rotation to ensure proper 360° coverage
2. **Configurable warning count** per exam
3. **Device detection** during warning (phone, tablet, extra screens)
4. **Audio warning** in addition to visual prompt
5. **Penalty system** if candidate fails to show complete rotation
6. **Image blur** of surrounding environment for privacy (optional)
7. **Timestamp overlay** on recorded frames for integrity proof

## Compliance & Privacy

### Data Handling
- Recorded frames stored locally during exam
- Included in downloadable JSON report
- Never sent to external servers
- Can be deleted after exam if desired
- Used only for academic integrity verification

### Student Privacy
- Recording only captures environment, not personal items
- Timestamp proves when recording occurred
- Part of official exam record
- Subject to standard academic records retention policy

## Testing Checklist

- [x] Warnings only appear after first 20% of exam
- [x] Exactly 4 warnings per 45-minute exam
- [x] Warnings appear at randomized times
- [x] Timer counts down correctly (10 seconds)
- [x] Progress bar fills correctly
- [x] Video frames capture at ~5fps
- [x] Approximately 50 frames per warning
- [x] Modal closes automatically after 10 seconds
- [x] Frames stored in event log
- [x] Frames appear in final report
- [x] Frames included in JSON export
- [x] NO trust score penalty applied
- [x] Works in both backend and client-side modes
- [x] Works with WebSocket streaming

---

**Version**: 1.0  
**Date**: 15 March 2026  
**System**: ExamGuard Pro v7
