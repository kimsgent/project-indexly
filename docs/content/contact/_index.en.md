---
title: "Contact"
type: docs
categories:
    - Contact
tags:
    - E-Mail
---


<div class="contact-wrapper">
  <div class="contact-info">
    <h2>Have questions or feedback?</h2>
    <p>📧 Email: <a href="mailto:gentkims@gmail.com">gentkims@gmail.com</a></p>
    <hr class="thin-line" />
    <div class="contact-buttons">
      <a href="https://linkedin.com/in/kimsgent" target="_blank" rel="noopener" class="contact-btn">
        <i class="fab fa-linkedin"></i>
      </a>
      <a href="https://sites.google.com/view/kimsgent" target="_blank" rel="noopener" class="contact-btn">
        <i class="fab fa-google"></i>
      </a>
      <a href="https://github.com/kimsgent/project-indexly" target="_blank" rel="noopener" class="contact-btn">
        <i class="fab fa-github"></i>
      </a>
      <a href="https://pypi.org/project/indexly/" target="_blank" rel="noopener" class="contact-btn">
        <i class="fab fa-python"></i>
      </a>
    </div>
    <p>💬 Use our contact form below:</p>
  </div>
  <form name="contact" method="POST" data-netlify="true" data-netlify-recaptcha="true" class="contact-form">
    <div class="form-group">
      <label for="name">Name</label>
      <input type="text" id="name" name="name" required />
    </div>
    <div class="form-group">
      <label for="email">Email</label>
      <input type="email" id="email" name="email" required />
    </div>
    <div class="form-group">
      <label for="message">Message</label>
      <textarea id="message" name="message" required></textarea>
    </div>
    <div data-netlify-recaptcha="true" class="recaptcha"></div>
    <button type="submit" class="submit-btn">Send</button>
  </form>
</div>

