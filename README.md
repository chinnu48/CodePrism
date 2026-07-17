# CodePrism

**A comprehensive competitive programming practice platform with real-time performance analytics, multi-platform integrations, and intelligent skill assessment.**

CodePrism is a full-featured web application designed to help competitive programmers track their practice, analyze their performance trends, and identify skill gaps across different problem domains. Built with Python and featuring both a CLI and modern web UI, it combines code execution, analytics, and multi-platform support in one unified system.

## 🎯 Key Features

### Core Practice Environment
- **Interactive Problem Solving**: Browse and solve coding problems with real-time test execution
- **Dual Interface**: 
  - **Web UI** (Streamlit): Modern, visually polished interface with advanced analytics
  - **CLI**: Command-line interface for quick practice sessions
- **Code Execution**: Safe, sandboxed Python code evaluation with timeout protection
- **Test Case Validation**: Instant feedback on test case pass/fail with detailed error reporting

### Advanced Analytics & Insights
- **Performance Metrics**:
  - Accuracy tracking across attempts
  - Speed Index: Ratio of actual time to predicted time
  - Confidence Calibration: How well your confidence matches actual performance
  - Time Deviation: Average drift between predicted and actual solve times
  - Error Recurrence Analysis: Track patterns in failure modes

- **Topic-Based Analysis**:
  - Per-topic accuracy breakdowns
  - Topic mastery scores
  - Weakness identification
  - Performance trends by domain

- **Structural Code Analysis**:
  - Recursion usage detection
  - Loop depth and count tracking
  - Dictionary/data structure usage
  - Sorting and binary search pattern recognition
  - Nesting depth analysis

- **PDF Report Generation**: Download comprehensive skill intelligence reports

### Multi-Platform Integration
- **LeetCode Import**: Pull accepted submissions from LeetCode into your analytics
  - Public mode for recent submissions
  - Optional advanced auth for fuller history
- **Codeforces Import**: Import submissions from Codeforces handles
- **Unified Timeline**: All practice (local + imported) appears in one analytics dashboard

### User Management
- **Secure Authentication**: User registration and login with password hashing
- **Admin Interface**: Add/edit problems, manage problem bank
- **Role-Based Access**: Admin and regular user roles
- **Session Persistence**: Secure session tracking across practice attempts

## 📁 Project Structure

```
CodePrism/
├── main.py                      # CLI entry point
├── app.py                        # Streamlit web application
├── database.py                   # Database operations & user management
├── executor.py                   # Code execution engine with sandbox
├── problem_engine.py             # Problem loading and management
├── analytics.py                  # Analytics & performance metrics
├── platform_integrations.py      # LeetCode & Codeforces API integration
└── problems/                     # Problem bank storage
```

### Core Modules

#### `main.py` - Command-Line Interface
- Problem selection and browsing
- Code submission via stdin
- Test execution with result display
- Structural feature extraction
- Local database logging

#### `app.py` - Web Application (Streamlit)
- ~1400 lines of comprehensive UI code
- Custom CSS styling with gradient backgrounds and animations
- Authentication system with login/registration
- Problem explorer with filtering (topic, difficulty, search)
- Live code editor with Ctrl+Enter evaluation
- Interactive dashboard with charts and metrics
- Attempt history viewer
- Admin panel for problem management
- PDF report export functionality

#### `database.py` - Data Layer
- PostgreSQL/SQLite support
- User authentication with secure password hashing
- Problem CRUD operations
- Attempt logging with structural features
- Analytics queries for metrics computation

#### `executor.py` - Code Execution Engine
- Safe Python code sandboxing
- Test case execution with timeout protection
- Exception capturing and error classification
- Input/output matching and validation

#### `analytics.py` - Performance Analytics
- Accuracy computation per topic
- Speed index calculation
- Confidence calibration scoring
- Error recurrence indexing
- Topic mastery scoring
- Performance trend analysis
- Structural feature extraction (loops, recursion, etc.)
- CLI and PDF report generation

#### `platform_integrations.py` - External APIs
- LeetCode public API client
- LeetCode advanced auth (session cookie, CSRF token)
- Codeforces API integration
- Submission parsing and normalization
- Import result tracking with notes

#### `problem_engine.py` - Problem Management
- Problem loading from internal bank
- Problem retrieval by ID
- Problem metadata management

## 🚀 Getting Started

### Prerequisites
- Python 3.9+
- PostgreSQL (optional; SQLite by default)
- pip or poetry

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/chinnu48/CodePrism.git
   cd CodePrism
   ```

2. **Install dependencies**
   ```bash
   pip install streamlit
   ```

3. **Set up environment (optional)**
   ```bash
   # Use PostgreSQL instead of SQLite
   export SKILL_LAB_DATABASE_URL="postgresql://user:password@localhost/codeprism"
   
   # Enable UI safe mode (disables custom styling)
   export SKILL_LAB_UI_SAFE_MODE=1
   ```

### Running the Application

#### Web UI (Recommended)
```bash
streamlit run app.py
```
Access the application at `http://localhost:8501`

#### CLI Mode
```bash
python main.py
```

## 📊 Usage Workflow

### Web UI Workflow
1. **Register/Login**: Create an account or sign in
2. **Browse Problems**: Filter by topic, difficulty, or search keywords
3. **Select & Solve**: Choose a problem and write your solution
4. **Evaluate**: Click "Evaluate" to run test cases
5. **Review Results**: See pass/fail status, error details, structural analysis
6. **Track Progress**: Monitor accuracy, speed, and confidence trends on the dashboard
7. **Import External**: Import from LeetCode or Codeforces under "Integrations"
8. **Generate Reports**: Export PDF skill intelligence reports

### CLI Workflow
1. **Start Session**: Run `python main.py`
2. **Select Problem**: Choose from displayed list
3. **Write Code**: Paste Python code (define `solve(...)` function)
4. **Set Metadata**: Enter predicted time and confidence level
5. **View Results**: See test case results and structural analysis
6. **Auto-Log**: Submission automatically recorded to database

## 🔧 Admin Features

### Problem Management
- Add new problems to the bank
- Edit existing problem metadata (title, topic, difficulty, description)
- Manage concept tags for better organization
- Update test cases in JSON format
- Filter and search existing problems

### Problem Format
```json
{
  "id": 1,
  "title": "Two Sum",
  "topic": "Array",
  "difficulty": "Easy",
  "expected_time": 10,
  "concept_tags": ["hash_map", "array"],
  "description": "Find two numbers that add up to target.",
  "test_cases": [
    {"input": "[2,7,11,15], 9", "output": "[0,1]"},
    {"input": "[3,2,4], 6", "output": "[1,2]"}
  ]
}
```

## 📈 Analytics Explained

### Speed Index
Ratio of (actual_time / predicted_time). Lower is better. Example: predicted 15 min, took 10 min = speed index 0.67 (faster).

### Confidence Calibration
Score from 0-100 measuring if your confidence levels match actual correctness. 50 = random guessing, 100 = perfect alignment.

### Error Recurrence Index
Tracks how often you encounter the same error types. Higher values indicate systematic issues to address.

### Topic Mastery Score
Accuracy-weighted metric per topic accounting for problem difficulty and attempt count.

### Performance Trends
Direction analysis (↑ improving, ↓ declining, → stable) with accuracy and speed deltas per topic.

## 🔐 Security & Privacy

- **Password Hashing**: Passwords stored as secure hashes (not plaintext)
- **Session Management**: Secure session state tracking
- **Code Sandboxing**: User code executed in isolated environment with timeout
- **Private Data**: User submissions and analytics tied to authenticated accounts
- **Optional Auth**: LeetCode/Codeforces imports use optional advanced auth

## 🗄️ Database Schema

### Core Tables
- **users**: id, username, password_hash, role, created_at
- **problems**: id, title, topic, difficulty, expected_time, concept_tags, description, test_cases
- **attempts**: id, user_id, problem_id, correct, time_taken, predicted_time, confidence, error_tag, structural_features, timestamp
- **sessions**: User session metadata for web UI

## 🎨 UI Customization

The web UI features custom styling with:
- Modern gradient backgrounds
- Animated orb elements
- Glass-morphism cards
- Difficulty-based color coding
- Responsive grid layouts
- Custom fonts (Syne, Instrument Sans, JetBrains Mono)

Disable custom styling with: `export SKILL_LAB_UI_SAFE_MODE=1`

## 📚 Example: Solving a Problem

### CLI Example
```
Available Problems
------------------
 1. Two Sum | Array | Easy | expected=10 min
 2. Binary Search | Search | Easy | expected=15 min

Select problem id: 1

Selected Problem
----------------
Title      : Two Sum
Topic      : Array
Difficulty : Easy
Expected   : 10 minutes
Tags       : hash_map, array
Description: Find two numbers that add up to target.

Paste Python code. Define solve(...). Type END on a new line to finish.
def solve(nums, target):
    seen = {}
    for num in nums:
        complement = target - num
        if complement in seen:
            return [seen[complement], nums.index(num)]
        seen[num] = nums.index(num)
END

Predicted solve time (minutes): 8
Confidence (0-100): 85

Execution Results
-----------------
Case 1: PASS
Case 2: PASS

Submission Summary
------------------
Correct        : True
Time Taken     : 7.45 minutes
Logged Error   : None

[Phase 2] Structural Code Signals
- recursion_usage: False
- loop_count: 1
- nested_depth: 1
- dictionary_usage: True
- sorting_calls: 0
- binary_search_pattern: False
```

## 🌐 Supported Platforms for Import
- **LeetCode**: Public submissions + optional advanced auth
- **Codeforces**: Full submission history by handle

## 🐛 Error Handling

The executor classifies errors into tags:
- **timeout**: Code exceeded execution time limit
- **runtime_error**: Exception during execution
- **type_error**: Type mismatch or invalid operation
- **index_error**: Array/list index out of bounds
- **key_error**: Dictionary key not found
- **value_error**: Invalid value passed
- **syntax_error**: Code syntax issues
- **assertion_error**: Test assertion failed

## 📝 License

[Add your license here]

## 👤 Author

**Chinnu48** - [GitHub Profile](https://github.com/chinnu48)

## 🤝 Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bugs and feature requests.

## 🎓 Use Cases

- **Competitive Programming Practice**: Systematic problem-solving with analytics
- **Interview Preparation**: Track progress across different problem types
- **Skill Assessment**: Identify weak areas and track improvement
- **Performance Benchmarking**: Compare confidence vs. actual performance
- **Multi-Platform Consolidation**: Unified analytics from LeetCode, Codeforces, and local practice

---

**Built with Python, Streamlit, and PostgreSQL** 🐍 ⚡ 🗄️
