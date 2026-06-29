"""
Session Management System for Multi-turn Conversations
Handles conversation threading, context tracking, and session persistence
"""

from datetime import datetime, timedelta
import uuid
from typing import Dict, List, Optional
from auth_routes import db

class ConversationSession:
    """Manages individual conversation sessions with context tracking"""
    
    def __init__(self, user_id: str, session_id: str = None):
        self.user_id = user_id
        self.session_id = session_id or str(uuid.uuid4())
        self.context_window = []  # Last 10 messages for context
        self.session_metadata = {
            'created_at': datetime.now().isoformat(),
            'last_active': datetime.now().isoformat(),
            'message_count': 0,
            'topics': [],
            'user_preferences': {}
        }
    
    def add_message(self, role: str, content: str, intent: str = None, confidence: float = None):
        """Add a message to conversation history"""
        message = {
            'role': role,  # 'user' or 'assistant'
            'content': content,
            'timestamp': datetime.now().isoformat(),
            'intent': intent,
            'confidence': confidence
        }
        
        # Keep only last 10 messages for context
        self.context_window.append(message)
        if len(self.context_window) > 10:
            self.context_window.pop(0)
        
        self.session_metadata['message_count'] += 1
        self.session_metadata['last_active'] = datetime.now().isoformat()
        
        # Store in database
        self._persist_message(message)
        
        return message
    
    def get_context(self, num_messages: int = 5) -> List[Dict]:
        """Get recent conversation context"""
        return self.context_window[-num_messages:]
    
    def get_full_conversation(self) -> List[Dict]:
        """Retrieve full conversation from database"""
        try:
            # Get all messages for this session from Firestore
            messages_ref = db.collection('chat_sessions').document(self.session_id).collection('messages')
            messages = messages_ref.order_by('timestamp').stream()
            
            return [msg.to_dict() for msg in messages]
        except Exception as e:
            print(f"Error retrieving conversation: {e}")
            return self.context_window
    
    def _persist_message(self, message: Dict):
        """Store message in Firestore"""
        try:
            # Store in chat_sessions collection
            session_ref = db.collection('chat_sessions').document(self.session_id)
            
            # Update session metadata
            session_ref.set({
                'user_id': self.user_id,
                'metadata': self.session_metadata
            }, merge=True)
            
            # Store individual message
            messages_ref = session_ref.collection('messages')
            messages_ref.add(message)
            
        except Exception as e:
            print(f"Error persisting message: {e}")
    
    def update_topics(self, detected_topics: List[str]):
        """Track conversation topics"""
        current_topics = set(self.session_metadata.get('topics', []))
        current_topics.update(detected_topics)
        self.session_metadata['topics'] = list(current_topics)
    
    def get_session_summary(self) -> Dict:
        """Get session statistics"""
        return {
            'session_id': self.session_id,
            'user_id': self.user_id,
            'duration': self._calculate_duration(),
            'message_count': self.session_metadata['message_count'],
            'topics': self.session_metadata['topics'],
            'created_at': self.session_metadata['created_at'],
            'last_active': self.session_metadata['last_active']
        }
    
    def _calculate_duration(self) -> str:
        """Calculate session duration"""
        try:
            start = datetime.fromisoformat(self.session_metadata['created_at'])
            end = datetime.fromisoformat(self.session_metadata['last_active'])
            duration = end - start
            
            minutes = int(duration.total_seconds() / 60)
            if minutes < 60:
                return f"{minutes} minutes"
            else:
                hours = minutes // 60
                mins = minutes % 60
                return f"{hours}h {mins}m"
        except:
            return "Unknown"


class SessionManager:
    """Manages multiple conversation sessions"""
    
    def __init__(self):
        self.active_sessions: Dict[str, ConversationSession] = {}
        self.session_timeout = timedelta(hours=24)  # Sessions expire after 24 hours
    
    def get_or_create_session(self, user_id: str, session_id: str = None) -> ConversationSession:
        """Get existing session or create new one"""
        
        if session_id and session_id in self.active_sessions:
            session = self.active_sessions[session_id]
            # Check if session is still active
            if self._is_session_active(session):
                return session
        
        # Create new session
        new_session = ConversationSession(user_id, session_id)
        self.active_sessions[new_session.session_id] = new_session
        
        # Load existing context from database if session_id provided
        if session_id:
            self._load_session_context(new_session)
        
        return new_session
    
    def _is_session_active(self, session: ConversationSession) -> bool:
        """Check if session is still active"""
        try:
            last_active = datetime.fromisoformat(session.session_metadata['last_active'])
            return datetime.now() - last_active < self.session_timeout
        except:
            return False
    
    def _load_session_context(self, session: ConversationSession):
        """Load conversation context from database"""
        try:
            messages = session.get_full_conversation()
            # Load last 10 messages into context window
            session.context_window = messages[-10:] if len(messages) > 10 else messages
        except Exception as e:
            print(f"Error loading session context: {e}")
    
    def get_user_sessions(self, user_id: str) -> List[Dict]:
        """Get all sessions for a user"""
        try:
            from firebase_admin import firestore
            sessions_ref = db.collection('chat_sessions').where(filter=firestore.FieldFilter('user_id', '==', user_id))
            sessions = sessions_ref.stream()
            
            session_list = []
            for session_doc in sessions:
                session_data = session_doc.to_dict()
                metadata = session_data.get('metadata', {})
                
                session_list.append({
                    'session_id': session_doc.id,
                    'created_at': metadata.get('created_at'),
                    'last_active': metadata.get('last_active'),
                    'message_count': metadata.get('message_count', 0),
                    'topics': metadata.get('topics', [])
                })
            
            # Sort by last_active descending
            session_list.sort(key=lambda x: x.get('last_active', ''), reverse=True)
            return session_list
            
        except Exception as e:
            print(f"Error getting user sessions: {e}")
            return []
    
    def end_session(self, session_id: str):
        """Explicitly end a session"""
        if session_id in self.active_sessions:
            session = self.active_sessions[session_id]
            session.session_metadata['ended_at'] = datetime.now().isoformat()
            
            # Persist final state
            try:
                db.collection('chat_sessions').document(session_id).set({
                    'metadata': session.session_metadata,
                    'status': 'ended'
                }, merge=True)
            except Exception as e:
                print(f"Error ending session: {e}")
            
            # Remove from active sessions
            del self.active_sessions[session_id]
    
    def cleanup_expired_sessions(self):
        """Remove expired sessions from memory"""
        expired = []
        for session_id, session in self.active_sessions.items():
            if not self._is_session_active(session):
                expired.append(session_id)
        
        for session_id in expired:
            del self.active_sessions[session_id]


# Global session manager instance
session_manager = SessionManager()
