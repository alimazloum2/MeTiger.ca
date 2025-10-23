# MeTiger Inc. Website

A professional construction project management company website built with Flask and TailwindCSS.

## Features

- **Responsive Design**: Mobile-first approach with TailwindCSS
- **Modern UI/UX**: Clean, professional design with smooth animations
- **Interactive Chat Widget**: AI-powered chat assistant for customer inquiries
- **Contact Form**: Working contact form with validation
- **SEO Optimized**: Meta tags and structured content
- **Fast Loading**: Optimized for performance

## Pages

1. **Home**: Hero section, company introduction, services preview, and call-to-action
2. **Services**: Detailed service categories (Preconstruction, Project Controls, Coordination, Change Management, Closeout)
3. **Projects**: Portfolio showcase with 3 featured projects
4. **Contact**: Contact form, company information, and location details

## Technology Stack

- **Backend**: Flask (Python)
- **Frontend**: HTML5, TailwindCSS, JavaScript
- **Deployment**: Nginx + Gunicorn
- **Database**: None (static content with form handling)

## Quick Start

### Development

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd metiger-site
   ```

2. **Create virtual environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application**:
   ```bash
   python app.py
   ```

5. **Open in browser**: http://localhost:8000

### Production Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed deployment instructions using Nginx and Gunicorn on Ubuntu.

## Project Structure

```
metiger-site/
├── app.py                 # Flask application
├── requirements.txt       # Python dependencies
├── templates/            # HTML templates
│   ├── base.html         # Base template with navigation and footer
│   ├── index.html        # Home page
│   ├── services.html     # Services page
│   ├── projects.html     # Projects page
│   └── contact.html      # Contact page
├── static/              # Static files (CSS, JS, images)
├── venv/                # Virtual environment
├── README.md            # This file
└── DEPLOYMENT.md        # Deployment guide
```

## Features in Detail

### Chat Widget
- Floating chat button in bottom-right corner
- AI-style responses based on user input
- Keyword-based response system
- Smooth animations and transitions

### Contact Form
- Full form validation
- Project type and budget selection
- Newsletter subscription option
- Success/error message handling
- Mobile-responsive design

### Responsive Design
- Mobile-first approach
- Tablet and desktop optimizations
- Touch-friendly navigation
- Optimized images and assets

## Customization

### Colors
The website uses a custom color scheme defined in the base template:
- Primary Blue: `#004c97` (metiger-blue)
- Accent Orange: `#ff6b35` (metiger-orange)

### Content
- Update company information in templates
- Modify project details in `projects.html`
- Adjust service descriptions in `services.html`
- Update contact information in `contact.html` and `base.html`

### Styling
- All styles use TailwindCSS classes
- Custom CSS can be added to the `<style>` section in `base.html`
- Responsive breakpoints: sm (640px), md (768px), lg (1024px), xl (1280px)

## Browser Support

- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+
- Mobile browsers (iOS Safari, Chrome Mobile)

## Performance

- Optimized images and assets
- Minified CSS and JavaScript
- Efficient caching headers
- Fast loading times

## Security

- CSRF protection on forms
- Input validation and sanitization
- Secure headers configuration
- Environment variable management

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is proprietary to MeTiger Inc. All rights reserved.

## Support

For technical support or questions about the website, contact:
- Email: info@metiger.com
- Phone: (555) 123-4567

---

**MeTiger Inc.** - Construction Project Management Done Right





