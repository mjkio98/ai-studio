"""
Progress tracking system for streaming updates.
Handles real-time progress tracking with Server-Sent Events (SSE) support.
"""

import json
import time
import threading
from threading import Thread, Event

# Progress tracking system for streaming updates
progress_store = {}
cancelled_tasks = set()  # Track cancelled tasks

# Efficient cancellation system using threading Events
task_stop_signals = {}  # task_id -> threading.Event

# Enhanced concurrent processing system
processing_queue = []  # List of task_ids waiting to be processed
active_processing_tasks = set()  # Set of currently processing task_ids
queue_lock = threading.Lock()  # Thread-safe queue operations
MAX_CONCURRENT_TASKS = 5  # Default max concurrent tasks (configurable)

# Configuration for concurrent processing
CONCURRENT_PROCESSING_CONFIG = {
    'max_concurrent_tasks': MAX_CONCURRENT_TASKS,
    'max_queue_size': 50,  # Maximum tasks that can be queued
    'enable_concurrent_processing': True  # Feature flag
}

class ProgressTracker:
    def __init__(self, task_id):
        self.task_id = task_id
        self.progress = {
            'status': 'queued',
            'step': '',
            'percentage': 0,
            'message': 'Joining queue...',
            'partial_result': '',
            'completed': False,
            'error': None,
            'cancelled': False,
            'start_time': time.time(),  # Add start time for cleanup
            'queue_position': 0,
            'estimated_wait_minutes': 0
        }
        progress_store[task_id] = self.progress
        
        # Create efficient stop signal (no polling needed!)
        self.stop_event = Event()
        task_stop_signals[task_id] = self.stop_event
    
    def update(self, step, percentage, message, partial_result=None):
        """Update progress with current step information"""
        self.progress.update({
            'status': 'processing',
            'step': step,
            'percentage': percentage,
            'message': message,
            'partial_result': partial_result if partial_result is not None else self.progress.get('partial_result', ''),
            'queue_position': get_queue_position(self.task_id),
            'estimated_wait_minutes': get_estimated_wait_time(self.task_id)
        })
    
    def update_queue_status(self):
        """Update queue position and wait time"""
        self.progress.update({
            'queue_position': get_queue_position(self.task_id),
            'estimated_wait_minutes': get_estimated_wait_time(self.task_id)
        })
        
        position = self.progress['queue_position']
        wait_time = self.progress['estimated_wait_minutes']
        
        if position == 0:
            self.progress['message'] = 'Starting processing now...'
            self.progress['status'] = 'processing'
        else:
            self.progress['message'] = f'Queue position: #{position} (estimated wait: {wait_time} minutes)'
            self.progress['status'] = 'queued'
    
    def complete(self, result):
        """Mark task as completed with final result"""
        self.progress.update({
            'status': 'completed',
            'step': 'completed',
            'percentage': 100,
            'message': 'Processing completed successfully!',
            'partial_result': result,
            'completed': True,
            'queue_position': 0,
            'estimated_wait_minutes': 0
        })
        
        # Mark task as complete in queue and start next
        next_task = complete_current_task(self.task_id)
        if next_task:
            print(f"🎯 QUEUE: Task {self.task_id} completed, starting {next_task}")
    
    def error(self, error_message):
        """Mark task as failed with error message"""
        self.progress.update({
            'status': 'error',
            'error': error_message,
            'completed': True,
            'queue_position': 0,
            'estimated_wait_minutes': 0
        })
        
        # Remove from queue and start next
        next_task = complete_current_task(self.task_id)
        if next_task:
            print(f"🎯 QUEUE: Task {self.task_id} failed, starting {next_task}")
    
    def cancel(self):
        """Mark task as cancelled"""
        self.progress.update({
            'status': 'cancelled',
            'completed': True,
            'cancelled': True,
            'queue_position': 0,
            'estimated_wait_minutes': 0
        })
        cancelled_tasks.add(self.task_id)
        
        # Remove from queue and start next
        next_task = remove_from_queue(self.task_id)
        if next_task:
            print(f"🎯 QUEUE: Task {self.task_id} cancelled, starting {next_task}")
    
    def is_cancelled(self):
        """Check if task is cancelled - ONLY call at natural breakpoints!"""
        return self.task_id in cancelled_tasks or self.progress.get('cancelled', False)
    
    def wait_or_cancel(self, timeout=0.1):
        """Efficient cancellation check - waits for stop signal OR timeout
        Returns True if should continue, False if cancelled"""
        if self.stop_event.wait(timeout):  # Signal received = cancelled
            return False
        return True  # No signal = continue
    
    def check_stop_at_breakpoint(self):
        """Ultra-fast cancellation check at natural breakpoints
        Use this instead of is_cancelled() for better performance"""
        is_stopped = self.stop_event.is_set()
        if is_stopped:
            print(f"🛑 BREAKPOINT: Task {self.task_id} detected stop signal")
        return is_stopped

def cleanup_progress(task_id, delay=5):
    """Clean up progress store after a delay"""
    def cleanup():
        time.sleep(delay)
        progress_store.pop(task_id, None)
        cancelled_tasks.discard(task_id)
        # Clean up stop signals to free memory
        task_stop_signals.pop(task_id, None)
    
    Thread(target=cleanup, daemon=True).start()

def add_to_queue(task_id):
    """Add task to processing queue with concurrent processing support"""
    global processing_queue, active_processing_tasks
    
    with queue_lock:
        config = CONCURRENT_PROCESSING_CONFIG
        
        # Check if concurrent processing is enabled
        if not config['enable_concurrent_processing']:
            # Fall back to old single-task behavior
            if len(active_processing_tasks) == 0:
                active_processing_tasks.add(task_id)
                return 0  # Position 0 means processing now
            else:
                processing_queue.append(task_id)
                return len(processing_queue)
        
        # Concurrent processing logic
        if len(active_processing_tasks) < config['max_concurrent_tasks']:
            # Can start processing immediately
            active_processing_tasks.add(task_id)
            print(f"🎯 CONCURRENT: Starting task {task_id} immediately (active: {len(active_processing_tasks)}/{config['max_concurrent_tasks']})")
            return 0  # Position 0 means processing now
        else:
            # Need to queue
            if len(processing_queue) >= config['max_queue_size']:
                # Queue is full, reject the task
                return -1  # Indicates queue is full
            
            processing_queue.append(task_id)
            queue_position = len(processing_queue)
            print(f"🎯 CONCURRENT: Queued task {task_id} at position {queue_position} (active: {len(active_processing_tasks)}/{config['max_concurrent_tasks']})")
            return queue_position

def remove_from_queue(task_id):
    """Remove task from queue (for cancellation) with concurrent processing support"""
    global processing_queue, active_processing_tasks
    
    with queue_lock:
        # Remove from active tasks if it's there
        if task_id in active_processing_tasks:
            active_processing_tasks.remove(task_id)
            print(f"🎯 CONCURRENT: Removed active task {task_id} (active: {len(active_processing_tasks)}/{CONCURRENT_PROCESSING_CONFIG['max_concurrent_tasks']})")
            
            # Start next task from queue if available
            if processing_queue:
                next_task_id = processing_queue.pop(0)
                active_processing_tasks.add(next_task_id)
                print(f"🎯 CONCURRENT: Started queued task {next_task_id} (active: {len(active_processing_tasks)}/{CONCURRENT_PROCESSING_CONFIG['max_concurrent_tasks']})")
                return next_task_id
        else:
            # Remove from waiting queue
            if task_id in processing_queue:
                processing_queue.remove(task_id)
                print(f"🎯 CONCURRENT: Removed queued task {task_id} (queue: {len(processing_queue)})")
        
        return None

def get_queue_position(task_id):
    """Get current position in queue with concurrent processing support"""
    global processing_queue, active_processing_tasks
    
    with queue_lock:
        if task_id in active_processing_tasks:
            return 0  # Currently processing
        elif task_id in processing_queue:
            return processing_queue.index(task_id) + 1  # Position in queue
        else:
            return -1  # Not in queue

def get_estimated_wait_time(task_id):
    """Get estimated wait time in minutes with concurrent processing support"""
    position = get_queue_position(task_id)
    if position <= 0:
        return 0  # Processing now or not in queue
    
    # With concurrent processing, estimate based on available slots
    config = CONCURRENT_PROCESSING_CONFIG
    if config['enable_concurrent_processing']:
        # Estimate 2 minutes per task for concurrent processing (faster turnaround)
        avg_task_time = 2
        concurrent_slots = config['max_concurrent_tasks']
        
        # Calculate wait time based on position and available slots
        wait_time = max(1, (position * avg_task_time) // concurrent_slots)
        return wait_time
    else:
        # Single task processing - 3 minutes per task
        return position * 3

def complete_current_task(task_id):
    """Mark current task as complete and start next in queue with concurrent processing support"""
    global active_processing_tasks, processing_queue
    
    with queue_lock:
        if task_id in active_processing_tasks:
            active_processing_tasks.remove(task_id)
            print(f"🎯 CONCURRENT: Completed task {task_id} (active: {len(active_processing_tasks)}/{CONCURRENT_PROCESSING_CONFIG['max_concurrent_tasks']})")
            
            # Start next task if available and there's capacity
            if processing_queue and len(active_processing_tasks) < CONCURRENT_PROCESSING_CONFIG['max_concurrent_tasks']:
                next_task_id = processing_queue.pop(0)
                active_processing_tasks.add(next_task_id)
                
                # Update next task to processing status
                if next_task_id in progress_store:
                    progress_store[next_task_id].update({
                        'queue_position': 0,
                        'estimated_wait_minutes': 0,
                        'message': 'Starting processing...',
                        'status': 'processing'
                    })
                    print(f"🎯 CONCURRENT: Started next task {next_task_id} (active: {len(active_processing_tasks)}/{CONCURRENT_PROCESSING_CONFIG['max_concurrent_tasks']})")
                
                return next_task_id
        return None

def cleanup_stale_tasks():
    """Clean up tasks that have been running for too long (over 10 minutes)"""
    global active_processing_tasks
    current_time = time.time()
    stale_tasks = []
    
    for task_id, progress in list(progress_store.items()):
        # If task has no timestamp, add one
        if 'start_time' not in progress:
            progress['start_time'] = current_time
            continue
            
        # If task is older than 10 minutes and not completed, mark as stale
        if (current_time - progress.get('start_time', current_time)) > 600:  # 10 minutes
            if not progress.get('completed', False):
                print(f"🧹 CLEANUP: Marking stale task as failed: {task_id}")
                progress.update({
                    'status': 'error',
                    'error': 'Task timed out after 10 minutes',
                    'completed': True
                })
                stale_tasks.append(task_id)
                
                # Remove from active tasks and queue
                with queue_lock:
                    active_processing_tasks.discard(task_id)
                remove_from_queue(task_id)
    
    # Clean up stale tasks after a short delay
    for task_id in stale_tasks:
        cleanup_progress(task_id, delay=1)
    
    return len(stale_tasks)

def set_max_concurrent_tasks(max_tasks):
    """Set the maximum number of concurrent tasks"""
    global CONCURRENT_PROCESSING_CONFIG
    if max_tasks < 1:
        max_tasks = 1
    elif max_tasks > 50:
        max_tasks = 50
    
    CONCURRENT_PROCESSING_CONFIG['max_concurrent_tasks'] = max_tasks
    print(f"🔧 CONFIG: Set max concurrent tasks to {max_tasks}")

def enable_concurrent_processing(enabled=True):
    """Enable or disable concurrent processing"""
    global CONCURRENT_PROCESSING_CONFIG
    CONCURRENT_PROCESSING_CONFIG['enable_concurrent_processing'] = enabled
    status = "enabled" if enabled else "disabled"
    print(f"🔧 CONFIG: Concurrent processing {status}")

def get_processing_status():
    """Get current processing status"""
    with queue_lock:
        return {
            'concurrent_processing_enabled': CONCURRENT_PROCESSING_CONFIG['enable_concurrent_processing'],
            'max_concurrent_tasks': CONCURRENT_PROCESSING_CONFIG['max_concurrent_tasks'],
            'max_queue_size': CONCURRENT_PROCESSING_CONFIG['max_queue_size'],
            'active_tasks_count': len(active_processing_tasks),
            'queued_tasks_count': len(processing_queue),
            'active_task_ids': list(active_processing_tasks),
            'queued_task_ids': processing_queue.copy()
        }

def wait_for_processing_slot(task_id, timeout=300):
    """Wait for a processing slot to become available"""
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        position = get_queue_position(task_id)
        
        if position == 0:  # Task is now active
            return True
        elif position == -1:  # Task was removed/cancelled
            return False
        
        # Check if task was cancelled while waiting
        if task_id in cancelled_tasks:
            return False
        
        # Update queue status and wait
        if task_id in progress_store:
            progress_store[task_id].update({
                'queue_position': position,
                'estimated_wait_minutes': get_estimated_wait_time(task_id),
                'message': f'Queue position: #{position} (estimated wait: {get_estimated_wait_time(task_id)} minutes)',
                'status': 'queued'
            })
        
        time.sleep(2)  # Check every 2 seconds
    
    # Timeout reached
    return False

def generate_progress_stream(task_id):
    """Generate Server-Sent Events stream for progress updates"""
    last_update = None
    while True:
        if task_id in progress_store:
            current_progress = progress_store[task_id].copy()
            
            # Only send updates if something changed
            if current_progress != last_update:
                print(f"🔍 DEBUG: SSE sending update for task {task_id}: {current_progress.get('message', '')}")
                if current_progress.get('partial_result'):
                    print(f"🔍 DEBUG: SSE includes partial result: {type(current_progress.get('partial_result'))}")
                
                try:
                    # Try to serialize to JSON to catch any serialization issues
                    json_data = json.dumps(current_progress, default=str)
                    yield f"data: {json_data}\n\n"
                    print(f"🔍 DEBUG: SSE data sent successfully")
                except Exception as e:
                    print(f"❌ ERROR: Failed to serialize SSE data: {e}")
                    # Send error-free version without partial_result
                    safe_progress = {k: v for k, v in current_progress.items() if k != 'partial_result'}
                    yield f"data: {json.dumps(safe_progress)}\n\n"
                
                last_update = current_progress.copy()
            
            # Stop streaming if task is completed or errored
            if current_progress.get('completed', False):
                # Clean up after 5 seconds
                cleanup_progress(task_id)
                break
        
        time.sleep(0.5)  # Check for updates every 500ms

def cancel_task_by_id(task_id):
    """Cancel a running task by ID - INSTANT signal, no polling!"""
    if task_id in progress_store:
        # Mark as cancelled in the cancelled_tasks set
        cancelled_tasks.add(task_id)
        
        # Send INSTANT stop signal (zero-cost operation!)
        if task_id in task_stop_signals:
            task_stop_signals[task_id].set()
            print(f"🛑 INSTANT STOP: Signal sent to task {task_id}")
        
        # Update progress to reflect cancellation
        progress_store[task_id].update({
            'status': 'cancelled',
            'message': 'Task cancelled by user',
            'completed': True,
            'cancelled': True
        })
        return True
    return False

# Global registry of active tasks with their processing threads
active_task_threads = {}
force_stopped_tasks = set()

def register_task_thread(task_id, thread_info=None):
    """Register a task with its processing context for force stopping"""
    active_task_threads[task_id] = {
        'registered_at': time.time(),
        'thread_info': thread_info,
        'force_stopped': False
    }
    print(f"🔍 DEBUG: Registered task {task_id} for force stop capability")

def unregister_task_thread(task_id):
    """Unregister a task when it completes"""
    active_task_threads.pop(task_id, None)
    force_stopped_tasks.discard(task_id)
    print(f"🔍 DEBUG: Unregistered task {task_id} from force stop registry")

def force_stop_task_by_id(task_id):
    """Force stop a running task more aggressively"""
    if task_id in progress_store:
        # First, try regular cancellation
        cancelled_tasks.add(task_id)
        force_stopped_tasks.add(task_id)
        
        # Update progress to reflect force stop
        progress_store[task_id].update({
            'status': 'force_stopped',
            'message': 'Task force stopped by user',
            'completed': True,
            'cancelled': True,
            'force_stopped': True
        })
        
        # Mark in the active threads registry
        if task_id in active_task_threads:
            active_task_threads[task_id]['force_stopped'] = True
        
        print(f"🛑 FORCE STOP: Task {task_id} marked for immediate termination")
        
        # Clean up immediately (no delay)
        cleanup_progress(task_id, delay=0)
        
        return True
    return False

def is_force_stopped(task_id):
    """Check if a task has been force stopped"""
    return (task_id in force_stopped_tasks or 
            (task_id in active_task_threads and active_task_threads[task_id].get('force_stopped', False)))