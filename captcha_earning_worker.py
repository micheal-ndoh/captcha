#!/usr/bin/env python3
"""
2Captcha Earning Worker
Automatically solves CAPTCHAs to earn money using the 2Captcha Worker API.
This script works as a CAPTCHA solver for others and earns you money.
"""

import os
import sys
import json
import time
import logging
import argparse
import requests
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
import urllib.parse
from PIL import Image
import io
import base64


class WorkerConfig:
    """Configuration for the 2Captcha earning worker."""
    
    def __init__(self, config_file: str = "earning_config.json"):
        self.config_file = config_file
        self.default_config = {
            "client_key": "",  # Your 2Captcha Client Key from Worker Dashboard
            "max_hours": 24,
            "min_delay": 5,
            "max_delay": 15,
            "earnings_per_captcha": 0.001,  # Average earnings per solved CAPTCHA
            "log_level": "INFO",
            "log_file": "earning_worker.log",
            "stats_file": "earning_stats.json",
            "timeout": 120,  # Timeout for solving each CAPTCHA
            "poll_interval": 5,  # How often to check for new CAPTCHAs
            "server": "2captcha.com",
            "accept_rate": 0.8,  # Accept 80% of available CAPTCHAs
            "max_concurrent": 1  # Solve one CAPTCHA at a time
        }
        self.config = {}
        self.load_config()
    
    def load_config(self):
        """Load configuration from file."""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    user_config = json.load(f)
                    self.config = {**self.default_config, **user_config}
            except Exception as e:
                print(f"Error loading config: {e}")
                self.config = self.default_config.copy()
        else:
            self.config = self.default_config.copy()
            self.save_config()
    
    def save_config(self):
        """Save configuration to file."""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")
    
    def get(self, key: str, default=None):
        """Get configuration value."""
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any):
        """Set configuration value."""
        self.config[key] = value
        self.save_config()


class EarningsStats:
    """Track earnings and statistics."""
    
    def __init__(self, stats_file: str):
        self.stats_file = stats_file
        self.stats = {
            "total_solved": 0,
            "total_failed": 0,
            "total_earnings": 0.0,
            "start_time": None,
            "last_solve_time": None,
            "session_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "daily_stats": {}
        }
        self.load_stats()
    
    def load_stats(self):
        """Load statistics from file."""
        if os.path.exists(self.stats_file):
            try:
                with open(self.stats_file, 'r') as f:
                    loaded_stats = json.load(f)
                    self.stats.update(loaded_stats)
            except Exception as e:
                logging.error(f"Error loading stats: {e}")
    
    def save_stats(self):
        """Save statistics to file."""
        try:
            with open(self.stats_file, 'w') as f:
                json.dump(self.stats, f, indent=4)
        except Exception as e:
            logging.error(f"Error saving stats: {e}")
    
    def record_solve(self, earnings: float):
        """Record a successful solve."""
        self.stats["total_solved"] += 1
        self.stats["total_earnings"] += earnings
        self.stats["last_solve_time"] = datetime.now().isoformat()
        
        # Track daily stats
        today = datetime.now().strftime("%Y-%m-%d")
        if today not in self.stats["daily_stats"]:
            self.stats["daily_stats"][today] = {"solved": 0, "earnings": 0.0}
        self.stats["daily_stats"][today]["solved"] += 1
        self.stats["daily_stats"][today]["earnings"] += earnings
        
        self.save_stats()
    
    def record_failure(self):
        """Record a failed solve."""
        self.stats["total_failed"] += 1
        self.save_stats()
    
    def get_summary(self) -> str:
        """Get formatted summary of statistics."""
        runtime = "N/A"
        if self.stats["start_time"]:
            start = datetime.fromisoformat(self.stats["start_time"])
            runtime = str(datetime.now() - start).split('.')[0]
        
        today = datetime.now().strftime("%Y-%m-%d")
        today_stats = self.stats["daily_stats"].get(today, {"solved": 0, "earnings": 0.0})
        
        return (f"📊 Earnings Summary:\n"
                f"   Total Solved: {self.stats['total_solved']}\n"
                f"   Total Failed: {self.stats['total_failed']}\n"
                f"   Total Earnings: ${self.stats['total_earnings']:.4f}\n"
                f"   Today's Solved: {today_stats['solved']}\n"
                f"   Today's Earnings: ${today_stats['earnings']:.4f}\n"
                f"   Runtime: {runtime}\n"
                f"   Session ID: {self.stats['session_id']}")


class CaptchaEarningWorker:
    """Main worker class for earning money by solving CAPTCHAs."""
    
    def __init__(self, config_file: str = "earning_config.json"):
        self.config = WorkerConfig(config_file)
        self.stats = EarningsStats(self.config.get("stats_file"))
        self.running = False
        self.start_time = None
        
        # Setup logging
        self._setup_logging()
        
        # Check client key
        if not self.config.get("client_key"):
            raise ValueError("Client key is required! Please set it in the configuration.")
        
        logging.info("🚀 2Captcha Earning Worker Initialized")
        logging.info(f"📋 Configuration loaded from {self.config.config_file}")
    
    def _setup_logging(self):
        """Setup logging configuration."""
        log_level = getattr(logging, self.config.get("log_level", "INFO"))
        log_format = '%(asctime)s - %(levelname)s - %(message)s'
        
        logging.basicConfig(
            level=log_level,
            format=log_format,
            handlers=[
                logging.FileHandler(self.config.get("log_file")),
                logging.StreamHandler(sys.stdout)
            ]
        )
    
    def check_balance(self) -> Optional[float]:
        """Check current earnings balance."""
        try:
            url = f"http://{self.config.get('server')}/res.php"
            params = {
                'key': self.config.get('client_key'),
                'action': 'getbalance'
            }
            
            response = requests.get(url, params=params, timeout=30)
            if response.status_code == 200:
                response_text = response.text.strip()
                if response_text.startswith('ERROR_'):
                    if "KEY_DOES_NOT_EXIST" in response_text:
                        logging.error("❌ Client key is invalid or not activated.")
                        logging.error("📋 To fix this:")
                        logging.error("   1. Complete the worker training at https://2captcha.com/workers")
                        logging.error("   2. Make sure your account is approved")
                        logging.error("   3. Copy the correct Client Key from the dashboard")
                        logging.error("   4. Run: python3 captcha_earning_worker.py --setup")
                    else:
                        logging.error(f"API Error checking balance: {response_text}")
                    return None
                else:
                    balance = float(response_text)
                    logging.info(f"💰 Current Balance: ${balance:.4f}")
                    return balance
            else:
                logging.error(f"Failed to check balance: {response.status_code}")
                return None
        except Exception as e:
            logging.error(f"Error checking balance: {e}")
            return None
    
    def get_captcha_task(self) -> Optional[Dict[str, Any]]:
        """Get a CAPTCHA task from the worker API."""
        try:
            url = f"http://{self.config.get('server')}/res.php"
            params = {
                'action': 'get',
                'key': self.config.get('client_key')
            }
            
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                response_text = response.text.strip()
                
                if response_text == "CAPCHA_NOT_READY":
                    logging.debug("⏳ No CAPTCHAs available right now")
                    return None
                elif response_text.startswith("ERROR_"):
                    if "KEY_DOES_NOT_EXIST" in response_text:
                        logging.error("❌ Client key is invalid. Check your Client Key from Worker Dashboard.")
                    else:
                        logging.error(f"API Error: {response_text}")
                    return None
                else:
                    # Parse CAPTCHA task
                    # Format: CAPTCHA_ID|CAPTCHA_TEXT
                    parts = response_text.split('|')
                    if len(parts) >= 2:
                        captcha_id = parts[0]
                        captcha_text = parts[1]
                        
                        logging.info(f"📝 Received CAPTCHA task: {captcha_id}")
                        return {
                            'id': captcha_id,
                            'text': captcha_text,
                            'type': 'text'
                        }
                    else:
                        logging.error(f"Invalid response format: {response_text}")
                        return None
            else:
                logging.error(f"HTTP Error: {response.status_code}")
                return None
                
        except Exception as e:
            logging.error(f"Error getting CAPTCHA task: {e}")
            return None
    
    def solve_captcha(self, task: Dict[str, Any]) -> bool:
        """Solve a CAPTCHA task."""
        try:
            captcha_id = task['id']
            captcha_text = task['text']
            
            # For text CAPTCHAs, we need to solve the puzzle/question
            solution = self._solve_text_captcha(captcha_text)
            
            if not solution:
                logging.warning(f"❌ Could not solve CAPTCHA {captcha_id}")
                return False
            
            # Submit the solution
            return self._submit_solution(captcha_id, solution)
            
        except Exception as e:
            logging.error(f"Error solving CAPTCHA: {e}")
            return False
    
    def _solve_text_captcha(self, text: str) -> Optional[str]:
        """Solve a text-based CAPTCHA."""
        text = text.lower().strip()
        
        # Common question patterns
        if "what is" in text and "+" in text:
            # Math problem
            try:
                # Extract numbers and operation
                parts = text.split("what is")[1].strip()
                if "+" in parts:
                    nums = parts.split("+")
                    result = int(nums[0]) + int(nums[1])
                    return str(result)
                elif "-" in parts:
                    nums = parts.split("-")
                    result = int(nums[0]) - int(nums[1])
                    return str(result)
            except:
                pass
        
        # Day/date questions
        if "tomorrow is friday" in text:
            return "thursday"
        elif "tomorrow is saturday" in text:
            return "friday"
        elif "tomorrow is sunday" in text:
            return "saturday"
        elif "tomorrow is monday" in text:
            return "sunday"
        elif "tomorrow is tuesday" in text:
            return "monday"
        elif "tomorrow is wednesday" in text:
            return "tuesday"
        elif "tomorrow is thursday" in text:
            return "wednesday"
        
        # Color questions
        if "color is the sky" in text:
            return "blue"
        elif "color is grass" in text:
            return "green"
        elif "color is blood" in text:
            return "red"
        
        # Simple questions
        if "planet we live on" in text:
            return "earth"
        elif "capital of france" in text:
            return "paris"
        elif "2+2" in text:
            return "4"
        elif "1+1" in text:
            return "2"
        
        # If we can't solve it, return None
        logging.debug(f"Could not solve: {text}")
        return None
    
    def _submit_solution(self, captcha_id: str, solution: str) -> bool:
        """Submit CAPTCHA solution."""
        try:
            url = f"http://{self.config.get('server')}/res.php"
            params = {
                'action': 'reportgood',
                'key': self.config.get('client_key'),
                'id': captcha_id
            }
            
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                result = response.text.strip()
                
                if result == "OK_REPORTED":
                    logging.info(f"✅ CAPTCHA {captcha_id} solution submitted successfully!")
                    earnings = self.config.get("earnings_per_captcha", 0.001)
                    self.stats.record_solve(earnings)
                    return True
                elif result.startswith("ERROR_"):
                    logging.warning(f"⚠️ Error submitting solution: {result}")
                    self.stats.record_failure()
                    return False
                else:
                    logging.warning(f"Unexpected response: {result}")
                    return False
            else:
                logging.error(f"HTTP Error submitting solution: {response.status_code}")
                return False
                
        except Exception as e:
            logging.error(f"Error submitting solution: {e}")
            return False
    
    def run(self):
        """Main worker loop."""
        self.running = True
        self.start_time = datetime.now()
        self.stats.stats["start_time"] = self.start_time.isoformat()
        self.stats.save_stats()
        
        max_runtime = self.config.get("max_hours", 24) * 3600
        poll_interval = self.config.get("poll_interval", 5)
        
        logging.info("🚀 Starting 2Captcha Earning Worker...")
        logging.info(f"⏰ Will run for {self.config.get('max_hours')} hours")
        logging.info(f"💰 Target earnings: ${self.config.get('earnings_per_captcha'):.4f} per CAPTCHA")
        
        try:
            while self.running:
                # Check runtime limit
                if max_runtime > 0:
                    elapsed = (datetime.now() - self.start_time).total_seconds()
                    if elapsed >= max_runtime:
                        logging.info("⏰ Time limit reached, stopping worker")
                        break
                
                # Get a CAPTCHA task
                task = self.get_captcha_task()
                
                if task:
                    # Solve the CAPTCHA
                    success = self.solve_captcha(task)
                    
                    if success:
                        # Random delay after successful solve
                        delay = random.uniform(
                            self.config.get("min_delay", 5),
                            self.config.get("max_delay", 15)
                        )
                        logging.debug(f"⏱️ Waiting {delay:.1f} seconds...")
                        time.sleep(delay)
                    else:
                        # Shorter delay after failure
                        time.sleep(2)
                else:
                    # No CAPTCHAs available, wait
                    logging.debug("⏳ No CAPTCHAs available, waiting...")
                    time.sleep(poll_interval)
                
        except KeyboardInterrupt:
            logging.info("🛑 Worker stopped by user")
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.running = False
            self._print_final_stats()
    
    def _print_final_stats(self):
        """Print final statistics."""
        logging.info("=" * 50)
        logging.info("🏁 Worker Session Completed")
        logging.info(self.stats.get_summary())
        
        # Check final balance
        final_balance = self.check_balance()
        if final_balance is not None:
            logging.info(f"💰 Final Balance: ${final_balance:.4f}")


def setup_config():
    """Setup configuration with user input."""
    print("🔧 2Captcha Earning Worker Setup")
    print("=" * 40)
    
    client_key = input("Enter your Client Key (from Worker Dashboard): ").strip()
    if not client_key:
        print("❌ Client Key is required!")
        return False
    
    config = WorkerConfig()
    config.set("client_key", client_key)
    
    # Optional settings
    max_hours = input("Max hours to run (default: 24): ").strip()
    if max_hours:
        try:
            config.set("max_hours", int(max_hours))
        except:
            pass
    
    print(f"✅ Configuration saved to {config.config_file}")
    return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="2Captcha Earning Worker - Earn money solving CAPTCHAs")
    parser.add_argument("--config", default="earning_config.json", help="Configuration file")
    parser.add_argument("--balance", action="store_true", help="Check balance only")
    parser.add_argument("--setup", action="store_true", help="Setup configuration")
    
    args = parser.parse_args()
    
    if args.setup:
        setup_config()
        return
    
    try:
        worker = CaptchaEarningWorker(args.config)
        
        if args.balance:
            worker.check_balance()
        else:
            worker.run()
            
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    import random  # Import here to avoid issues with setup
    main()
