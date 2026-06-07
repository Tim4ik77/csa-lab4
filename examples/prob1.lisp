(defconst IO_OUT 8)

(defvar high 0)
(defvar factor 0)
(defvar pal 0)
(defvar q 0)
(defvar best 0)
(defvar found 0)
(defvar inner_done 0)

(defun putc (ch)
  (mem-set IO_OUT ch))

(defun print_uint_rec (x)
  (if (< x 10)
    (putc (+ x '0'))
    (begin
      (print_uint_rec (/ x 10))
      (putc (+ (mod x 10) '0')))))

(defun print_uint (x)
  (if (= x 0)
    (putc '0')
    (print_uint_rec x)))

(defun reverse3 (x)
  (+ (* (mod x 10) 100)
     (+ (* (mod (/ x 10) 10) 10)
        (/ x 100))))

(defun make_palindrome (left)
  (+ (* left 1000) (reverse3 left)))

(defun main ()
  (begin
    (setq high 999)
    (setq found 0)
    (while (= found 0)
      (if (< high 100)
        (setq found 1)
        (begin
          (setq pal (make_palindrome high))
          (setq factor 990)
          (setq inner_done 0)
          (while (= inner_done 0)
            (if (< factor 100)
              (setq inner_done 1)
              (begin
                (if (= (mod pal factor) 0)
                  (begin
                    (setq q (/ pal factor))
                    (if (< q 100)
                      0
                      (if (< q 1000)
                        (begin
                          (setq best pal)
                          (setq found 1)
                          (setq inner_done 1))
                        0)))
                  0)
                (setq factor (- factor 11)))))
          (if (= found 0)
            (setq high (- high 1))
            0))))
    (print_uint best)
    (putc '\n')))
