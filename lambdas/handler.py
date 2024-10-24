import json
import logging
import traceback
import os
import requests
from typing import Dict, Any

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Alpaca API settings
ALPACA_API_KEY = os.getenv('ALPACA_API_KEY')
ALPACA_SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')
ALPACA_BASE_URL = 'https://paper-api.alpaca.markets'
HEADERS = {
    'APCA-API-KEY-ID': ALPACA_API_KEY,
    'APCA-API-SECRET-KEY': ALPACA_SECRET_KEY,
    'Content-Type': 'application/json'
}

def create_response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """Create a standardized API response"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Credentials': 'true'
        },
        'body': json.dumps(body)
    }

def execute_trade(message: Dict[str, Any]) -> Dict[str, Any]:
    """Execute trade using Alpaca API"""
    try:
        symbol = message['symbol']
        action = message['action'].lower()  # "buy" or "sell"
        qty = message['quantity']

        if action not in ["buy", "sell"]:
            return {"error": "Invalid action. Must be 'buy' or 'sell'"}

        # Check account status
        account_url = f"{ALPACA_BASE_URL}/v2/account"
        account_response = requests.get(account_url, headers=HEADERS)
        
        if account_response.status_code != 200:
            return {"error": f"Failed to get account status: {account_response.text}"}
            
        account = account_response.json()
        if account['status'] != 'ACTIVE':
            return {"error": "Account is not active"}

        # Place order
        order_url = f"{ALPACA_BASE_URL}/v2/orders"
        order_data = {
            "symbol": symbol,
            "qty": qty,
            "side": action,
            "type": "market",
            "time_in_force": "day"
        }
        order_data.update(message)
        logger.info(order_data)

        order_response = requests.post(order_url, headers=HEADERS, json=order_data)
        logger.info(order_response)
        
        if order_response.status_code != 200:
            logger.info(f"Failed to place order: {order_response.text}")
            return {"error": f"Failed to place order: {order_response.text}"}
            
        order = order_response.json()
        
        logger.info(f"Order submitted: {order}")
        return {
            "message": f"Successfully placed {action} order for {qty} shares of {symbol}",
            "order_id": order['id'],
            "order_status": order['status']
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"API request error: {str(e)}")
        return {"error": f"API request failed: {str(e)}"}
    except Exception as e:
        logger.error(f"Error executing trade: {str(e)}")
        logger.error(traceback.format_exc())
        return {"error": f"Failed to execute trade: {str(e)}"}

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle incoming messages and execute trade"""
    # Log the entire event for debugging
    logger.info("Received event:")
    logger.info(json.dumps(event, indent=2))
    
    try:
        # Handle different event types (direct invocation vs API Gateway)
        if isinstance(event, dict):
            # If it's a direct test invocation
            if 'symbol' in event and 'action' in event and 'quantity' in event:
                message = event
            # If it's from API Gateway
            elif 'body' in event:
                if isinstance(event['body'], str):
                    body = json.loads(event['body'])
                else:
                    body = event['body']
                
                message = body.get('message', body)
            else:
                return create_response(400, {'error': 'Invalid request format'})
        else:
            return create_response(400, {'error': 'Invalid event type'})

        logger.info(f"Processed message: {message}")
        
        # Required fields validation
        required_fields = ['symbol', 'action', 'quantity']
        missing_fields = [field for field in required_fields if field not in message]
        if missing_fields:
            return create_response(400, {
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            })
        
        # Execute the trade
        trade_response = execute_trade(message)
        
        if 'error' in trade_response:
            return create_response(400, trade_response)
            
        return create_response(200, {
            'message': trade_response['message'],
            'order_details': {
                'order_id': trade_response['order_id'],
                'status': trade_response['order_status']
            },
            'requestId': context.aws_request_id
        })
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON body: {str(e)}")
        return create_response(400, {'error': 'Invalid JSON in request body'})
        
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        logger.error(traceback.format_exc())
        return create_response(500, {
            'error': 'Internal server error',
            'requestId': context.aws_request_id
        })
