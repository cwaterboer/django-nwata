# Nwata: A Local-First Productivity Analytics Platform

## 1. Product Overview

Nwata is a privacy-focused productivity analytics platform designed to help individuals and organizations understand and optimize their work patterns. Unlike traditional cloud-based tracking tools, Nwata operates primarily on the user's local machine, collecting activity data through a lightweight desktop agent while providing insights through a web-based dashboard. The platform combines real-time activity monitoring with machine learning-driven feedback loops to deliver actionable productivity insights.

The system consists of two main components:
- **Nwata Agent**: A PyQt-based desktop application that runs locally on Windows, macOS, and Linux systems
- **Nwata Web**: A Django-powered web application providing user dashboards, analytics, and administrative controls

## 2. Problem Statement

Modern knowledge workers struggle with:
- **Lack of visibility** into how they actually spend their time across multiple applications and windows
- **Privacy concerns** with cloud-based tracking tools that upload sensitive activity data
- **Ineffective productivity tools** that don't adapt to individual work patterns or provide meaningful insights
- **Organizational challenges** in understanding team productivity without compromising individual privacy

Traditional productivity tracking solutions often require constant internet connectivity, raise data privacy concerns, and fail to provide contextual insights beyond basic time tracking.

## 3. Product Hypothesis

We hypothesized that a local-first approach to productivity analytics would address key adoption barriers:

- **Privacy-first design** would increase user trust and adoption rates
- **Context-aware tracking** (typing, scrolling, shortcuts, idle time per window) would provide richer insights than simple time tracking
- **Daily feedback loops** with machine learning would enable continuous improvement of productivity recommendations
- **Flexible licensing** (individual and organizational) would support both personal and enterprise use cases

## 4. Key Features

### Core Features (Implemented)
- **Activity Tracking**: Real-time monitoring of user activity across applications and windows
- **Context Monitoring**: Detailed tracking of typing events, scrolling, keyboard shortcuts, and idle time per window
- **Local Data Storage**: SQLite-based local database ensuring data remains on the user's machine
- **Web Dashboard**: Django-powered interface for viewing activity logs and analytics
- **REST API**: Backend endpoints for data synchronization and agent downloads

### Planned Features
- **Daily Feedback Loop**: ML-powered daily reflections and productivity insights
- **Organization Management**: Multi-user organizations with role-based access
- **Licensing System**: Individual and organizational subscription models
- **Advanced Analytics**: Trend analysis, productivity scoring, and recommendation engine

## 5. Product Architecture

Nwata follows a distributed architecture with clear separation between local and cloud components:

### Nwata Agent (Local Component)
- **Framework**: PyQt5 for cross-platform desktop application
- **Data Collection**: System hooks for window events, keyboard/mouse activity
- **Local Storage**: SQLite database for activity logs and user preferences
- **Synchronization**: Background thread for secure API communication
- **UI**: System tray interface with minimal user interaction

### Nwata Web (Cloud Component)
- **Framework**: Django with Django REST Framework
- **Database**: PostgreSQL for user accounts, organizations, and aggregated analytics
- **Authentication**: Django's built-in auth system with organization-based access control
- **API**: RESTful endpoints for agent synchronization and dashboard data
- **Frontend**: Django templates with responsive design for dashboard views

### Data Flow
1. Agent collects activity data locally
2. Data is aggregated by window/context and stored in local SQLite
3. Background sync thread uploads data to Django API
4. Web dashboard processes and displays analytics
5. ML models (future) analyze patterns for personalized insights

## 6. Product Decisions and Trade-offs

### Local-First Architecture
**Decision**: Prioritize local data collection and storage over cloud-based solutions
**Rationale**: Addresses privacy concerns and enables offline functionality
**Trade-offs**:
- Increased complexity in data synchronization
- Limited real-time collaboration features
- Higher development effort for cross-platform compatibility

### PyQt for Desktop Agent
**Decision**: Use PyQt5 over Electron or web technologies
**Rationale**: Better system integration, lower resource usage, native performance
**Trade-offs**:
- Platform-specific dependencies and compilation requirements
- Smaller developer community compared to web technologies
- Steeper learning curve for web developers

### Context-Aware Tracking
**Decision**: Track detailed context (typing, scrolling, shortcuts) per window rather than just time
**Rationale**: Provides richer data for productivity analysis and ML training
**Trade-offs**:
- Higher privacy sensitivity requiring careful data handling
- Increased local processing overhead
- More complex data models and API payloads

### SQLite for Local Storage
**Decision**: Use SQLite over more complex local databases
**Rationale**: Zero-configuration, cross-platform compatibility, sufficient performance
**Trade-offs**:
- Limited concurrent access (acceptable for single-user local app)
- No built-in migration system (requires custom handling)

## 7. Challenges Encountered

### Agent Download Hosting
**Challenge**: Initial attempt to host the agent binary using Google Cloud Storage resulted in authentication requirements, making downloads inaccessible to users.
**Solution**: Exploring alternative hosting solutions including GitHub Releases, Cloudflare R2, or self-hosted options to ensure public accessibility.

### Database Schema Evolution
**Challenge**: Adding context fields to the ActivityLog model required careful migration handling to avoid data loss during development.
**Solution**: Implemented automatic migration detection and execution in the Django backend, with fallback error handling in the agent sync process.

### Cross-Platform Window Detection
**Challenge**: Implementing reliable window title and application detection across Windows, macOS, and Linux platforms.
**Solution**: Leveraged platform-specific APIs (WinAPI, Cocoa, X11) through PyQt5's cross-platform abstractions, with fallback mechanisms for edge cases.

### Thread Safety in Context Monitoring
**Challenge**: Ensuring thread-safe aggregation of context signals (keyboard/mouse events) while maintaining performance.
**Solution**: Implemented atomic operations and careful synchronization in the ContextMonitor class to prevent race conditions.

## 8. Outcomes and Lessons Learned

### Technical Achievements
- Successfully implemented context-aware activity tracking with sub-second granularity
- Achieved cross-platform compatibility for the desktop agent
- Built a scalable Django backend capable of handling real-time data synchronization
- Demonstrated the feasibility of local-first productivity analytics

### Key Lessons
- **Privacy drives adoption**: The local-first approach has been well-received in initial testing, validating our hypothesis about privacy concerns
- **Context matters more than time**: Detailed activity context provides significantly more actionable insights than simple time tracking
- **Platform compatibility requires investment**: Cross-platform development demands careful abstraction and extensive testing
- **User experience is critical**: The agent's system tray interface must be unobtrusive yet discoverable

### Performance Metrics
- Agent resource usage: <5MB RAM, minimal CPU impact
- Sync efficiency: Batches data to minimize API calls and battery drain
- Dashboard responsiveness: Sub-second query times for activity data

## 9. Future Roadmap

### Phase 1: Core Completion (Q4 2025)
- [ ] Implement daily feedback loop with basic ML models
- [ ] Complete organization management and user roles
- [ ] Launch individual licensing and subscription system
- [ ] Add advanced analytics and trend visualization

### Phase 2: Intelligence Enhancement (Q1 2026)
- [ ] Integrate machine learning for productivity pattern recognition
- [ ] Add personalized recommendations and insights
- [ ] Implement smart notification system for productivity coaching
- [ ] Expand context tracking to include application-specific metrics

### Phase 3: Enterprise Features (Q4 2026)
- [ ] Multi-organization support with hierarchical management
- [ ] Team analytics and collaboration insights
- [ ] Advanced reporting and export capabilities
- [ ] Integration APIs for third-party productivity tools

### Phase 4: Ecosystem Expansion (2027)
- [ ] Mobile companion app for on-the-go insights
- [ ] Browser extension for web activity tracking
- [ ] Plugin architecture for custom productivity metrics
- [ ] Open API for third-party integrations

### Technical Debt and Improvements
- [ ] Migrate to more robust local database solution
- [ ] Implement end-to-end encryption for data synchronization
- [ ] Add comprehensive automated testing suite
- [ ] Optimize agent performance for low-end hardware

---

*This README represents the current state of Nwata as of March 2024. The project is actively under development, with features and timelines subject to change based on user feedback and technical requirements.*