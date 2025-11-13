from flask import Flask, request, jsonify
from flask_swagger_ui import get_swaggerui_blueprint
from datetime import datetime, timedelta
import json
import os

app = Flask(__name__)

# File lưu trữ dữ liệu
DATA_FILE = 'library_data.json'

# ==================== Swagger UI Configuration ====================
SWAGGER_URL = '/api/docs'
API_URL = '/static/openapi.yaml'

swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={
        'app_name': "Library Management API",
        'layout': "BaseLayout",
        'deepLinking': True
    }
)
app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)

# ==================== Data Management Functions ====================

def init_data():
    """Khởi tạo dữ liệu mẫu nếu file chưa tồn tại"""
    if not os.path.exists(DATA_FILE):
        data = {
            'books': [
                {'id': 1, 'title': 'Python Programming', 'author': 'John Smith', 'quantity': 5, 'available': 5},
                {'id': 2, 'title': 'Flask Web Development', 'author': 'Miguel Grinberg', 'quantity': 3, 'available': 3},
                {'id': 3, 'title': 'Data Structures and Algorithms', 'author': 'Robert Sedgewick', 'quantity': 4, 'available': 4}
            ],
            'borrowings': []
        }
        save_data(data)
        print("✅ Đã khởi tạo dữ liệu mẫu")
    return load_data()

def load_data():
    """Đọc dữ liệu từ file JSON"""
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_data(data):
    """Lưu dữ liệu vào file JSON"""
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ==================== ROOT ENDPOINT ====================

@app.route('/')
def home():
    """Endpoint gốc - Hướng dẫn sử dụng API"""
    return jsonify({
        'message': 'Welcome to Library Management API',
        'version': '1.0.0',
        'documentation': f'http://127.0.0.1:5000{SWAGGER_URL}',
        'endpoints': {
            'books': {
                'GET /api/books': 'Lấy danh sách tất cả sách',
                'POST /api/books': 'Thêm sách mới',
                'GET /api/books/{id}': 'Lấy thông tin sách theo ID',
                'PUT /api/books/{id}': 'Cập nhật thông tin sách',
                'DELETE /api/books/{id}': 'Xóa sách'
            },
            'borrowings': {
                'GET /api/borrowings': 'Lấy danh sách mượn/trả',
                'POST /api/borrowings': 'Mượn sách',
                'POST /api/borrowings/{id}/return': 'Trả sách'
            }
        },
        'swagger_ui': f'http://127.0.0.1:5000{SWAGGER_URL}'
    }), 200

# ==================== BOOKS API ENDPOINTS ====================

@app.route('/api/books', methods=['GET'])
def api_get_books():
    """GET /api/books - Lấy danh sách tất cả sách"""
    try:
        data = load_data()
        print(f"📚 Lấy danh sách sách: {len(data['books'])} cuốn")
        return jsonify(data['books']), 200
    except Exception as e:
        print(f"❌ Lỗi: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/books', methods=['POST'])
def api_create_book():
    """POST /api/books - Thêm sách mới"""
    try:
        if not request.json:
            return jsonify({'error': 'Request phải là JSON'}), 400
        
        required_fields = ['title', 'author', 'quantity']
        for field in required_fields:
            if field not in request.json:
                return jsonify({'error': f'Thiếu trường bắt buộc: {field}'}), 400
        
        data = load_data()
        new_book = {
            'id': max([b['id'] for b in data['books']], default=0) + 1,
            'title': request.json['title'],
            'author': request.json['author'],
            'quantity': int(request.json['quantity']),
            'available': int(request.json['quantity'])
        }
        
        data['books'].append(new_book)
        save_data(data)
        
        print(f"✅ Đã thêm sách mới: {new_book['title']} (ID: {new_book['id']})")
        return jsonify(new_book), 201
    except Exception as e:
        print(f"❌ Lỗi: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/books/<int:book_id>', methods=['GET'])
def api_get_book(book_id):
    """GET /api/books/{id} - Lấy thông tin sách theo ID"""
    try:
        data = load_data()
        book = next((b for b in data['books'] if b['id'] == book_id), None)
        
        if not book:
            print(f"❌ Không tìm thấy sách ID: {book_id}")
            return jsonify({'error': f'Không tìm thấy sách với ID: {book_id}'}), 404
        
        print(f"📖 Lấy thông tin sách: {book['title']} (ID: {book_id})")
        return jsonify(book), 200
    except Exception as e:
        print(f"❌ Lỗi: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/books/<int:book_id>', methods=['PUT'])
def api_update_book(book_id):
    """PUT /api/books/{id} - Cập nhật thông tin sách"""
    try:
        if not request.json:
            return jsonify({'error': 'Request phải là JSON'}), 400
        
        data = load_data()
        book = next((b for b in data['books'] if b['id'] == book_id), None)
        
        if not book:
            print(f"❌ Không tìm thấy sách ID: {book_id}")
            return jsonify({'error': f'Không tìm thấy sách với ID: {book_id}'}), 404
        
        # Cập nhật thông tin
        if 'title' in request.json:
            book['title'] = request.json['title']
        if 'author' in request.json:
            book['author'] = request.json['author']
        if 'quantity' in request.json:
            old_quantity = book['quantity']
            new_quantity = int(request.json['quantity'])
            diff = new_quantity - old_quantity
            book['quantity'] = new_quantity
            book['available'] += diff
        
        save_data(data)
        print(f"✅ Đã cập nhật sách: {book['title']} (ID: {book_id})")
        return jsonify(book), 200
    except Exception as e:
        print(f"❌ Lỗi: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/books/<int:book_id>', methods=['DELETE'])
def api_delete_book(book_id):
    """DELETE /api/books/{id} - Xóa sách"""
    try:
        data = load_data()
        book = next((b for b in data['books'] if b['id'] == book_id), None)
        
        if not book:
            print(f"❌ Không tìm thấy sách ID: {book_id}")
            return jsonify({'error': f'Không tìm thấy sách với ID: {book_id}'}), 404
        
        # Kiểm tra sách có đang được mượn không
        borrowings = [b for b in data['borrowings'] 
                     if b.get('bookId', b.get('book_id')) == book_id 
                     and not b.get('returned', False)]
        
        if borrowings:
            print(f"❌ Không thể xóa sách đang được mượn (ID: {book_id})")
            return jsonify({'error': 'Không thể xóa sách đang được mượn'}), 400
        
        data['books'] = [b for b in data['books'] if b['id'] != book_id]
        save_data(data)
        
        print(f"✅ Đã xóa sách: {book['title']} (ID: {book_id})")
        return jsonify({'message': 'Xóa sách thành công'}), 200
    except Exception as e:
        print(f"❌ Lỗi: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ==================== BORROWINGS API ENDPOINTS ====================

@app.route('/api/borrowings', methods=['GET'])
def api_get_borrowings():
    """GET /api/borrowings - Lấy danh sách mượn/trả"""
    try:
        data = load_data()
        borrowings = data['borrowings']
        
        # Lọc theo status nếu có
        status = request.args.get('status')
        if status == 'borrowed':
            borrowings = [b for b in borrowings if not b.get('returned', False)]
            print(f"📋 Lấy danh sách đang mượn: {len(borrowings)} phiếu")
        elif status == 'returned':
            borrowings = [b for b in borrowings if b.get('returned', False)]
            print(f"📋 Lấy danh sách đã trả: {len(borrowings)} phiếu")
        else:
            print(f"📋 Lấy tất cả phiếu mượn/trả: {len(borrowings)} phiếu")
        
        return jsonify(borrowings), 200
    except Exception as e:
        print(f"❌ Lỗi: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/borrowings', methods=['POST'])
def api_borrow_book():
    """POST /api/borrowings - Mượn sách"""
    try:
        if not request.json:
            return jsonify({'error': 'Request phải là JSON'}), 400
        
        required_fields = ['bookId', 'borrowerName']
        for field in required_fields:
            if field not in request.json:
                return jsonify({'error': f'Thiếu trường bắt buộc: {field}'}), 400
        
        data = load_data()
        book_id = int(request.json['bookId'])
        book = next((b for b in data['books'] if b['id'] == book_id), None)
        
        if not book:
            print(f"❌ Không tìm thấy sách ID: {book_id}")
            return jsonify({'error': f'Không tìm thấy sách với ID: {book_id}'}), 404
        
        if book['available'] <= 0:
            print(f"❌ Sách đã hết (ID: {book_id})")
            return jsonify({'error': 'Sách đã hết, không thể mượn'}), 400
        
        borrowing = {
            'id': max([b['id'] for b in data['borrowings']], default=0) + 1,
            'bookId': book_id,
            'bookTitle': book['title'],
            'borrowerName': request.json['borrowerName'],
            'borrowDate': datetime.now().isoformat() + 'Z',
            'dueDate': (datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d'),
            'returnDate': None,
            'returned': False
        }
        
        data['borrowings'].append(borrowing)
        book['available'] -= 1
        save_data(data)
        
        print(f"✅ {borrowing['borrowerName']} đã mượn: {book['title']} (Hạn trả: {borrowing['dueDate']})")
        return jsonify(borrowing), 201
    except Exception as e:
        print(f"❌ Lỗi: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/borrowings/<int:borrowing_id>/return', methods=['POST'])
def api_return_book(borrowing_id):
    """POST /api/borrowings/{id}/return - Trả sách"""
    try:
        data = load_data()
        borrowing = next((b for b in data['borrowings'] if b['id'] == borrowing_id), None)
        
        if not borrowing:
            print(f"❌ Không tìm thấy phiếu mượn ID: {borrowing_id}")
            return jsonify({'error': f'Không tìm thấy phiếu mượn với ID: {borrowing_id}'}), 404
        
        if borrowing.get('returned', False):
            print(f"❌ Sách đã được trả rồi (ID: {borrowing_id})")
            return jsonify({'error': 'Sách đã được trả rồi'}), 400
        
        borrowing['returned'] = True
        borrowing['returnDate'] = datetime.now().isoformat() + 'Z'
        
        # Tăng số sách có sẵn
        book_id = borrowing.get('bookId', borrowing.get('book_id'))
        book = next((b for b in data['books'] if b['id'] == book_id), None)
        if book:
            book['available'] += 1
        
        save_data(data)
        print(f"✅ {borrowing['borrowerName']} đã trả: {borrowing['bookTitle']}")
        return jsonify(borrowing), 200
    except Exception as e:
        print(f"❌ Lỗi: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint không tồn tại'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Lỗi server nội bộ'}), 500

# ==================== MAIN ====================

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 LIBRARY MANAGEMENT API - Starting...")
    print("="*60)
    
    # Khởi tạo dữ liệu
    init_data()
    
    print("\n📍 API Endpoints:")
    print("   - Home: http://127.0.0.1:5000/")
    print("   - Swagger UI: http://127.0.0.1:5000/api/docs")
    print("   - Books API: http://127.0.0.1:5000/api/books")
    print("   - Borrowings API: http://127.0.0.1:5000/api/borrowings")
    
    print("\n💡 Sử dụng:")
    print("   - Swagger UI: Mở trình duyệt -> http://127.0.0.1:5000/api/docs")
    print("   - curl: curl http://127.0.0.1:5000/api/books")
    print("   - Postman: Import URL -> http://127.0.0.1:5000/static/openapi.yaml")
    
    print("\n⏸️  Dừng server: Nhấn Ctrl+C")
    print("="*60 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=5000)