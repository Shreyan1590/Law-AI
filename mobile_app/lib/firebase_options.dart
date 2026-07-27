import 'package:firebase_core/firebase_core.dart' show FirebaseOptions;
import 'package:flutter/foundation.dart'
    show defaultTargetPlatform, kIsWeb, TargetPlatform;

class DefaultFirebaseOptions {
  static FirebaseOptions get currentPlatform {
    if (kIsWeb) {
      return web;
    }
    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
        return android;
      default:
        throw UnsupportedError(
          'DefaultFirebaseOptions are not supported for this platform.',
        );
    }
  }

  static const FirebaseOptions web = FirebaseOptions(
    apiKey: 'AIzaSyB6g-MDNDcypkJTpMR0oVXvI7z7qB9sX50',
    appId: '1:1063410976132:web:f16a15f1fafe51a53a49d1',
    messagingSenderId: '1063410976132',
    projectId: 'indian-constitution-law',
    authDomain: 'indian-constitution-law.firebaseapp.com',
    storageBucket: 'indian-constitution-law.firebasestorage.app',
    measurementId: 'G-XV3BWMR86K',
  );

  static const FirebaseOptions android = FirebaseOptions(
    apiKey: 'AIzaSyDOkSdWFjiMVjr4v0Va_gqIG2HVlCRcSek',
    appId: '1:1063410976132:android:2906f3e9ae806fec3a49d1',
    messagingSenderId: '1063410976132',
    projectId: 'indian-constitution-law',
    storageBucket: 'indian-constitution-law.firebasestorage.app',
  );
}
