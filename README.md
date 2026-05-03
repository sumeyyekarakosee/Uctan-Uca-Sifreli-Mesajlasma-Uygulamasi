# Uçtan Uca Şifreli Dosya ve Mesaj Uygulaması

Python ile geliştirilmiş, istemci-sunucu mimarisine sahip, uçtan uca şifreleme destekli masaüstü mesajlaşma ve dosya paylaşım uygulaması.

## Proje Hakkında

Bu proje, kullanıcıların ağ üzerinden güvenli biçimde mesajlaşmasını ve dosya paylaşmasını sağlamak amacıyla geliştirilmiştir. Uygulamada kullanıcı doğrulama, çevrimiçi kullanıcı listesi, şifreli mesaj gönderimi, şifreli dosya aktarımı ve sohbet geçmişi görüntüleme gibi özellikler bulunmaktadır.

Sunucu, yalnızca paketleri yönlendiren bir yapıdadır; mesaj ve dosya içeriklerinin çözülmesi istemci tarafında yapılır. Böylece uçtan uca şifreleme mantığı korunur.

## Özellikler

- Kullanıcı kayıt ve giriş sistemi
- Sunucuya bağlanma ve oturum başlatma
- Çevrimiçi kullanıcı listesini görüntüleme
- Uçtan uca şifreli mesajlaşma
- Uçtan uca şifreli dosya gönderme/alma
- Dosya transferi sırasında ilerleme takibi
- Sohbet geçmişini yerel olarak saklama
- Son 7 gün içindeki konuşmaları otomatik koruma
- Gelen dosyaları klasörde gösterme

## Kullanılan Teknolojiler

- Python
- Tkinter
- Socket
- JSON
- threading
- cryptography

## Proje Yapısı

- `server.py`  
  Sunucu uygulaması. Kullanıcı bağlantılarını kabul eder, giriş/kayıt işlemlerini yönetir ve paketleri alıcıya yönlendirir.

- `client.py`  
  İstemci uygulaması. Sunucuya bağlanır, mesaj ve dosya gönderir, gelen paketleri işler.

- `gui.py`  
  Grafik arayüzü içerir. Giriş ekranı, sohbet ekranı ve dosya gönderme bölümlerini yönetir.

- `crypto_utils.py`  
  RSA ve AES şifreleme yardımcı fonksiyonlarını içerir.

- `auth_utils.py`  
  Kullanıcı kayıt ve giriş işlemleri için şifre hashleme ve doğrulama fonksiyonlarını içerir.

- `file_utils.py`  
  Dosya okuma ve kayıt işlemlerini yönetir.

- `history_store.py`  
  Sohbet geçmişini yerel JSON dosyalarında tutar.

- `protocol.py`  
  Sunucu ve istemci arasında kullanılan paket yapısını tanımlar.

## Kurulum

### Gerekli Python sürümü
- Python 3.10 veya üzeri önerilir.

### Gerekli paketler
Projede kullanılan dış paket:

```bash
pip install cryptography
